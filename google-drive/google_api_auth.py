""" Copyright start
  Copyright (C) 2008 - 2022 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end """

import requests
from time import time, ctime
from os import path
from datetime import datetime
from base64 import b64encode
from connectors.core.connector import get_logger, ConnectorError

logger = get_logger('google-drive')

CONFIG_SUPPORTS_TOKEN = True
try:
    from connectors.core.utils import update_connnector_config
except:
    CONFIG_SUPPORTS_TOKEN = False
    configfile = path.join(path.dirname(path.abspath(__file__)), 'config.conf')

REFRESH_TOKEN_FLAG = False

# redirect url
DEFAULT_REDIRECT_URL = 'https://localhost'

# grant types
REFRESH_TOKEN = 'refresh_token'


class GoogleAuth:

    def __init__(self, config):
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        self.verify_ssl = config.get('verify_ssl')
        self.host = config.get("server")
        if "http://" in self.host or "https://" in self.host:
            self.host = "{0}".format(self.host)
        else:
            self.host = "https://{0}".format(self.host)
        self.refresh_token = ""
        self.code = config.get("code")
        self.token_url = 'https://accounts.google.com/o/oauth2/token'
        if not config.get("redirect_url"):
            self.redirect_url = DEFAULT_REDIRECT_URL
        else:
            self.redirect_url = config.get("redirect_url")

    def convert_ts_epoch(self, ts):
        datetime_object = datetime.strptime(ctime(ts), "%a %b %d %H:%M:%S %Y")
        return datetime_object.timestamp()

    def generate_token(self, REFRESH_TOKEN_FLAG):
        try:
            token_resp = acquire_token(self, REFRESH_TOKEN_FLAG)
            ts_now = time()
            token_resp['expiresOn'] = (ts_now + token_resp['expires_in']) if token_resp.get("expires_in") else None
            token_resp['accessToken'] = token_resp.get("access_token")
            token_resp.pop("access_token")
            return token_resp
        except Exception as err:
            logger.error("{0}".format(err))
            raise ConnectorError("{0}".format(err))

    def validate_token(self, connector_config, connector_info):
        try:
            ts_now = time()
            if not connector_config.get('accessToken'):
                logger.error('Error occurred while connecting server: Unauthorized')
                raise ConnectorError('Error occurred while connecting server: Unauthorized')
            expires = connector_config['expiresOn']
            expires_ts = self.convert_ts_epoch(expires)
            if ts_now > float(expires_ts):
                REFRESH_TOKEN_FLAG = True
                logger.info("Token expired at {0}".format(expires))
                self.refresh_token = connector_config['refresh_token']
                token_resp = self.generate_token(REFRESH_TOKEN_FLAG)
                connector_config['accessToken'] = token_resp['accessToken']
                connector_config['expiresOn'] = token_resp['expiresOn']
                if token_resp.get('refresh_token'):
                    connector_config['refresh_token'] = token_resp.get('refresh_token')
                update_connnector_config(connector_info['connector_name'], connector_info['connector_version'],
                                         connector_config,
                                         connector_config['config_id'])

                return "{0}".format(connector_config.get('accessToken'))
            else:
                logger.info("Token is valid till {0}".format(expires))
                return "{0}".format(connector_config.get('accessToken'))
        except Exception as err:
            logger.error("{0}".format(str(err)))
            raise ConnectorError("{0}".format(str(err)))


def acquire_token(self, REFRESH_TOKEN_FLAG):
    try:
        error_msg = ''
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_url,
            'grant_type': 'authorization_code'
        }

        if not REFRESH_TOKEN_FLAG:
            data["code"] = self.code
        else:
            data["grant_type"] = REFRESH_TOKEN,
            data["refresh_token"] = self.refresh_token

        response = requests.post('https://oauth2.googleapis.com/token', data=data, headers=headers, verify=self.verify_ssl)
        if response.status_code in [200, 204, 201]:
            return response.json()

        else:
            if response.text != "":
                err_resp = response.json()
                if err_resp and 'error' in err_resp:
                    failure_msg = err_resp.get('error_description')
                    error_msg = 'Response {0}: {1} \n Error Message: {2}'.format(response.status_code,
                                                                                 response.reason,
                                                                                 failure_msg if failure_msg else '')
                else:
                    error_msg = response.text
            else:
                error_msg = '{0}:{1}'.format(response.status_code, response.reason)
            raise ConnectorError(error_msg)

    except Exception as err:
        logger.error("{0}".format(str(err)))
        raise ConnectorError(str(err))


def check(config, connector_info):
    try:
        go = GoogleAuth(config)
        if CONFIG_SUPPORTS_TOKEN:
            if not 'accessToken' in config:
                token_resp = go.generate_token(REFRESH_TOKEN_FLAG)
                config['accessToken'] = token_resp.get('accessToken')
                config['expiresOn'] = token_resp.get('expiresOn')
                config['refresh_token'] = token_resp.get('refresh_token')
                update_connnector_config(connector_info['connector_name'], connector_info['connector_version'], config,
                                         config['config_id'])
                return True
            else:
                token_resp = go.validate_token(config, connector_info)
                return True
    except Exception as err:
        raise ConnectorError(str(err))
