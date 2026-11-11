import json
import logging
import os
import sys

import pandas as pd
from confluent_kafka import Consumer
from confluent_kafka import Producer
from prometheus_client import Counter, Gauge, Histogram, start_http_server

sys.path.append(os.path.abspath('./src'))  # noqa: PTH100
from preprocessing import run_preproc
from scorer import ensure_bootstrap, make_pred


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/service.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Set kafka configuration file
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TRANSACTIONS_TOPIC = os.getenv("KAFKA_TRANSACTIONS_TOPIC", "transactions")
SCORING_TOPIC = os.getenv("KAFKA_SCORING_TOPIC", "scoring")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
FRAUD_THRESHOLD = 0.5

TRANSACTIONS_PROCESSED = Counter(
    'fraud_detector_transactions_processed_total',
    'Number of processed transactions',
)
PROCESSING_SECONDS = Histogram(
    'fraud_detector_processing_seconds',
    'Processing time of one transaction',
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
SCORE = Histogram(
    'fraud_detector_score',
    'Distribution of fraud scores',
    buckets=[i / 20 for i in range(21)],
)
FRAUD_FLAGGED = Counter(
    'fraud_detector_fraud_flagged_total',
    'Number of transactions flagged as fraud',
)
FRAUD_SHARE = Gauge(
    'fraud_detector_fraud_share',
    'Share of transactions flagged as fraud since service start',
)
FLAGGED_AMOUNT = Counter(
    'fraud_detector_flagged_amount_total',
    'Sum of amounts of transactions flagged as fraud',
)
ERRORS = Counter(
    'fraud_detector_errors_total',
    'Number of messages that failed to process',
)
MODEL_SWITCHES = Counter(
    'fraud_detector_model_switches_total',
    'Hot swaps of the model without restart',
    ['version'],
)


class ProcessingService:
    def __init__(self):
        self.consumer_config = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'group.id': 'ml-scorer',
            'auto.offset.reset': 'earliest',
        }
        self.producer_config = {
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        }
        self.consumer = Consumer(self.consumer_config)
        self.consumer.subscribe([TRANSACTIONS_TOPIC])
        self.producer = Producer(self.producer_config)
        self.processed = 0
        self.flagged = 0
        self.model_version = None
        start_http_server(METRICS_PORT)
        logger.info("Prometheus metrics on port %s", METRICS_PORT)

    def track_model_version(self, model_version):
        """Increments the switch counter when a new model file is picked up."""
        if self.model_version is not None and model_version != self.model_version:
            MODEL_SWITCHES.labels(version=model_version).inc()
            logger.info("Model switched: %s -> %s", self.model_version, model_version)
        self.model_version = model_version

    def update_metrics(self, score, amount):
        """Updates Prometheus metrics for one scored transaction."""
        self.processed += 1
        TRANSACTIONS_PROCESSED.inc()
        SCORE.observe(score)
        if score > FRAUD_THRESHOLD:
            self.flagged += 1
            FRAUD_FLAGGED.inc()
            FLAGGED_AMOUNT.inc(amount)
        FRAUD_SHARE.set(self.flagged / self.processed)

    @PROCESSING_SECONDS.time()
    def process_message(self, msg):
        try:
            # Десериализация JSON
            data = json.loads(msg.value().decode('utf-8'))

            # Извлекаем ID и данные
            transaction_id = data['transaction_id']
            input_df = pd.DataFrame([data['data']])

            # Препроцессинг и предсказание
            processed_df = run_preproc(input_df)
            submission, y_proba, model_version = make_pred(processed_df, "kafka_stream")

            self.update_metrics(float(y_proba[0]), float(data['data']['amount']))
            self.track_model_version(model_version)

            # Добавляем ID и версию модели, которая отскорила запрос
            submission['transaction_id'] = transaction_id
            submission['model_version'] = model_version
            # Поля транзакции для фильтров на дашборде
            for column in ['us_state', 'merch', 'cat_id', 'amount']:
                submission[column] = data['data'][column]

            # Отправка результата в топик scoring
            self.producer.produce(
                SCORING_TOPIC,
                value=submission.to_json(orient='records'),
            )
            self.producer.flush()
            return True
        except Exception as e:
            ERRORS.inc()
            logger.exception(f"Error processing message: {e}")
            return False

    def process_messages(self):
        while True:
            msg = self.consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue
            
            self.process_message(msg)


if __name__ == "__main__":
    logger.info('Starting Kafka ML scoring service...')
    ensure_bootstrap()
    service = ProcessingService()
    try:
        service.process_messages()
    except KeyboardInterrupt:
        logger.info('Service stopped by user')
