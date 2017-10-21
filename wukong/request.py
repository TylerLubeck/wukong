import logging

from wukong.zookeeper import Zookeeper
from requests.exceptions import ConnectionError
from wukong.errors import SolrError
import requests
import random
import json
import time

try:
    from urlparse import urljoin
except:
    from urllib.parse import urljoin

logger = logging.getLogger()

def process_response(response):
    if response.status_code != 200:
        raise SolrError(response.reason)
    try:
        response_content = json.loads(response.text)
    except:
        logger.exception('Failed to parse solr text')
        raise SolrError("Parsing Error: %s" % response.text)

    return response_content


class SolrRequest(object):
    """
    Handle requests to SOLR and response from SOLR
    """
    def __init__(self, solr_hosts, zookeeper_hosts=None, timeout=15):
        self.client = requests.Session()
        self.master_hosts = solr_hosts
        self.servers = []
        self.timeout = timeout

        self.last_error = None
        # time to revert to old host list (in minutes) after an error
        self.check_hosts = 5

        if zookeeper_hosts is not None:
            logger.debug('Fetching solr from zookeeper')
            self.zookeeper = Zookeeper(zookeeper_hosts)
            self.master_hosts = self.zookeeper.get_active_hosts()
            logger.info(
                'Got solr nodes from zookeeper: %s',
                ','.join(self.master_hosts)
            )
        else:
            self.zookeeper = None

        if not self.master_hosts:
            logger.error('Unable to find any solr nodes to make requests to')
            raise SolrError("SOLR reporting all nodes as down")

        self.current_hosts = self.master_hosts  # Backwards Compat


    def request(self, path, params, method, body=None, headers=None):
        """
        Prepare data and send request to SOLR servers
        """
        request_headers = {
            'content-type': 'application/json',
        }
        if headers:
            request_headers.update(headers)


        request_params = {
            'wt': 'json',
            'omitHeader': True,
            'json.nl': 'map'
        }
        if params:
            request_params.update(params)
        
        response = None
        for host in self.master_hosts:
            full_path = urljoin(host, path)
            try:
                logger.debug(
                    'Sending request to solr. host="%s" path="%s"',
                    host,
                    path
                )

                response = self.client.request(
                    method,
                    full_path,
                    params=request_params,
                    headers=request_headers,
                    data=body,
                    timeout=self.timeout
                )

                logger.debug(
                    'Retrieved response from SOLR. host="%s" path="%s" '
                    'status_code="%s"',
                    host,
                    path,
                    response.status_code
                )

                if response.status_code == 200:
                    # We've had a successful request. No need to keep trying
                    break
                else:
                    logger.info(
                        'Unsucessful request to SOLR'
                        'status_code="%s" reason="%s"',
                        response.status_code,
                        response.reason
                    )
                    response = None

            except ConnectionError:
                response = None
                logger.info(
                    'Failed to connect to SOLR',
                    exc_info=True
                )

        if not response:
            raise SolrError('Unable to fetch from any SOLR nodes')

        return process_response(response)

    def post(self, path, params=None, body=None, headers=None):
        """
        Send a POST request to the SOLR servers
        """
        return self.request(path, params, 'POST', body=body, headers=headers)

    def get(self, path, params=None, headers=None):
        """
        Send a GET request to the SOLR servers
        """
        return self.request(path, params, 'GET', headers=headers)
