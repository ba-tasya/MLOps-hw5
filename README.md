# MLOps-hw5

## Описание
Мониторинг сервиса скоринга фродовых транзакций (за основу взято дз-3). Сервисы `fraud_detector` и `scoring_writer` отдают метрики в Prometheus, Node Exporter отдает метрики хоста, Grafana показывает дашборды, отметку смены модели и алерты. Источники данных, дашборды и алерты подключаются через provisioning (`grafana/provisioning`)

## Шаг 0
Создать `.env` и указать в `TRAIN_DATA_CSV` полный путь к `train.csv` (не загружается на гх из-за размера)
```bash
cp .env.example .env
```

## Шаг 1: запуск
```bash
docker compose up --build -d
```
* Grafana: http://localhost:3000 (`admin` / `admin`)
* Prometheus: http://localhost:9090 (Status -> Targets: `fraud_detector`, `scoring_writer`, `node_exporter` в состоянии UP)
* метрики сервисов: http://localhost:8000/metrics и http://localhost:8001/metrics
* Airflow: http://localhost:8081 (`admin` / `admin`)

## Шаг 2: само задание
### 1. Метрики
`fraud_detector` (порт 8000):
* `fraud_detector_transactions_processed_total` - обработанные транзакции
* `fraud_detector_processing_seconds` - время обработки одной транзакции
* `fraud_detector_score` - распределение скоров
* `fraud_detector_fraud_flagged_total`, `fraud_detector_fraud_share` - число и доля транзакций, помеченных как фрод
* `fraud_detector_model_switches_total{version}` - смена версии модели без перезапуска
* `fraud_detector_errors_total` - доп. метрика: сообщения, которые не удалось обработать. Без нее сервис, который падает на каждом сообщении, на графиках выглядит как пустой поток (панель Processing errors на дашборде 1)
<img width="314" height="121" alt="Screenshot 2026-11-11 at 20 00 55" src="https://github.com/user-attachments/assets/d8840bca-3d54-43a3-95f6-0203e219683c" />

* `fraud_detector_flagged_amount_total` - доп. метрика: сумма транзакций, помеченных как фрод, т е сколько денег модель предлагает заблокировать (панель Amount of transactions flagged as fraud на дашборде 1)
<img width="619" height="237" alt="Screenshot 2026-11-11 at 20 02 20" src="https://github.com/user-attachments/assets/6797134d-ecf4-4b89-8b1d-f49b9a767f56" />


`scoring_writer` (порт 8001):
* `scoring_writer_scores_written_total` - записанные скоры
* `scoring_writer_write_seconds` - время записи в PostgreSQL
* `scoring_writer_fraud_written_total` - выявленный фрод
* `scoring_writer_score` - распределение записанных скоров

Проверяем, что метрики растут вместе с потоком (запустить несколько раз):
```bash
curl -s localhost:8000/metrics | grep fraud_detector_transactions_processed_total
curl -s localhost:8001/metrics | grep scoring_writer_scores_written_total
```

### 2. Дашборды
Grafana -> Dashboards -> папка Fraud monitoring. JSON дашбордов собирает скрипт `grafana/build_dashboards.py`
* **1. Transaction processing** - скорость потока, время обработки, доля фрода, тепловая карта скоров, свои метрики, скоры и доля фрода по версиям модели из PostgreSQL
<img width="1301" height="720" alt="Screenshot 2026-11-11 at 20 04 52" src="https://github.com/user-attachments/assets/c1a3e50e-c1fc-4834-9f96-350bad939687" />


* **2. Results writing** - скорость и время записи в БД, выявленный фрод, тепловая карта записанных скоров
<img width="1303" height="411" alt="Screenshot 2026-11-11 at 20 05 12" src="https://github.com/user-attachments/assets/125c610c-efcb-4d0a-b70b-bfd6e576b286" />


* **3. System metrics** - CPU, память, сеть, диск (Node Exporter)
<img width="1302" height="410" alt="Screenshot 2026-11-11 at 20 05 30" src="https://github.com/user-attachments/assets/d0166387-526b-4f9e-8f85-2fc86b77a0f8" />

* **4. Fraud business analytics** - фильтры `state` и `merch` сверху, плотность скоров и TPS по выбранным штатам и мерчантам, доля фрода по `cat_id` за последние 1000 транзакций, сумма фрода по штатам (доп. график: где потенциальный ущерб больше)
<img width="1304" height="456" alt="Screenshot 2026-11-11 at 20 06 07" src="https://github.com/user-attachments/assets/b60be2c2-972f-40c1-8299-63099c1f05f5" />


Для панелей из PostgreSQL `scoring_writer` пишет в таблицу `scores` поля транзакции `us_state`, `merch`, `cat_id`, `amount`

### 3. Отметка смены модели
DAG `retrain_catboost` в Airflow запускается раз в 5 минут. Первый прогон всегда публикует новую модель вместо `initial`, сервис скоринга подхватывает ее без перезапуска, и на дашбордах 1 и 2 появляется оранжевая отметка `New model: <версия>` примерно на 30 секунд
```bash
docker compose exec airflow cat /opt/airflow/models/latest.txt
```

### 4. Алерты
Grafana -> Alerting -> Alert rules -> папка Fraud alerts

| Алерт | Условие | Как проверить |
|---|---|---|
| `High fraud share` | доля помеченных фродом транзакций за последнюю минуту > 5% в течение 30 с | обычно доля меньше 2%, поэтому поменять порог `0.05` на `0.001` в `grafana/provisioning/alerting/rules.yaml` и выполнить `docker compose restart grafana`, через ~1 минуту алерт в состоянии Firing |
| `Transaction stream stopped` | меньше 1 транзакции в секунду в течение 30 с | `docker compose stop transaction_simulator`, через ~1 минуту алерт в состоянии Firing, после `docker compose start transaction_simulator` возвращается в Normal |

<img width="1221" height="167" alt="image" src="https://github.com/user-attachments/assets/0564db09-9ea8-4645-8188-f2bb79eb95c2" />
