# Bulk inserts the data from ./data.xls into elasticsearch

import os
import time

import pandas as pd
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from loguru import logger

ELASTICSEARCH_HOST = os.environ.get('ELASTICSEARCH_HOST', 'localhost')
ELASTICSEARCH_PORT = os.environ.get('ELASTICSEARCH_PORT', '9200')
ES_HOST = f'http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}'
FILENAME = os.environ.get('DATA_FILE', 'data.xls')
INDEX_NAME = os.environ.get('INDEX_NAME', 'comp_pen_call_center')

DATE_FIELDS = (
    'Date/Time Closed',
    'Date/Time Opened',
    'VACX Case: Last Modified Date',
)


def main():
    # Read the data
    logger.info(f'Reading data from {FILENAME}')
    data = pd.read_excel(FILENAME)

    # Create the elasticsearch client
    logger.info(f'Creating elasticsearch client at {ES_HOST}')
    es = Elasticsearch(ES_HOST)
    # Drop the index
    logger.info(f'Dropping index {INDEX_NAME}')
    es.indices.delete(index=INDEX_NAME, ignore=[400, 404])

    # Create the index
    logger.info(f'Creating index {INDEX_NAME}')
    es.indices.create(index=INDEX_NAME, ignore=400)

    # Bulk insert the data
    logger.info(f'Bulk inserting data into {INDEX_NAME}')
    bulk(es, data_to_json(data), index=INDEX_NAME)


def data_to_json(data):
    for index, row in data.iterrows():
        for field in DATE_FIELDS:
            row[field] = row[field].isoformat()

        yield {'_index': INDEX_NAME, '_source': row.to_json()}


if __name__ == '__main__':
    time.sleep(30)  # Wait for elasticsearch to start
    logger.info('Starting')
    try:
        main()
    except Exception as e:
        logger.error(e)
    logger.info('Finished')
