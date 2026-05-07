""" Copyright start
  Copyright (C) 2008 - 2022 Fortinet Inc.
  All rights reserved.
  FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
  Copyright end """
from .google_api_auth import *
from oauth2client.client import AccessTokenCredentials
from googleapiclient import discovery
from googleapiclient.http import MediaFileUpload
from connectors.cyops_utilities.builtins import download_file_from_cyops, upload_file_to_cyops
import mimetypes
from googleapiclient.http import MediaIoBaseDownload
import io, os
from django.conf import settings


DRIVE_API_VERSION = 'V3'


def check_payload(payload):
    updated_payload = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            nested = check_payload(value)
            if len(nested.keys()) > 0:
                updated_payload[key] = nested
        elif value:
            updated_payload[key] = value
    return updated_payload


def _new_service(config, serviceName, version, connector_info):
    try:
        go = GoogleAuth(config)
        token = go.validate_token(config, connector_info)
        credentials = AccessTokenCredentials(token, 'FortiSOAR Integration')
        service = discovery.build(serviceName, version, credentials=credentials, cache_discovery=False)
        return service
    except Exception as err:
        logger.error(err)
        raise ConnectorError(err)


def get_all_files(config, params, connector_info):
    try:
        service = _new_service(config, 'drive', 'v3', connector_info)
        results = service.files().list(
        pageSize=params.get('pageSize'), fields="nextPageToken, files(id, name, mimeType)", orderBy='modifiedTime desc').execute()
        response = results.get('files', [])
        return response
    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))


def delete_file(config, params, connector_info):
    try:
        service = _new_service(config, 'drive', 'v3', connector_info)
        results = service.files().delete(fileId=params.get('fileId')).execute()
        return results
    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))


def empty_trash(config, params, connector_info):
    try:
        service = _new_service(config, 'drive', 'v3', connector_info)
        results = service.files().emptyTrash().execute()
        return results
    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))


def upload_file(config, params, connector_info):
    try:
        # create drive api client
        service = _new_service(config, 'drive', 'v3', connector_info)
        file_download_response = download_file_from_cyops(params.get('fileIRI'))
        if not file_download_response['filename']:
            raise Exception("File does not exist")

        file_path = '/tmp/'+file_download_response['filename']
        file_name = params.get('new_file_name')
        if not (file_name):
            file_name = file_download_response['filename']
        file_metadata = {'name': file_name}
        mime_type = mimetypes.guess_type(file_name)
        media = MediaFileUpload(file_path, mimetype=mime_type[0])
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return {"file_id" : file.get("id")}

    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))


def download_file(config, params, connector_info):
    try:
        # create drive api client
        service = _new_service(config, 'drive', 'v3', connector_info)
        file_id = params.get('file_id')
        file_metadata = service.files().get(fileId=file_id).execute()
        file_name = file_metadata['name']
        request = service.files().get_media(fileId=file_id)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            logger.debug(F'Download {int(status.progress() * 100)}.')
        if file:
            path = os.path.join(settings.TMP_FILE_ROOT, file_name)
            logger.debug("Path: {0}".format(path))
            with open(path, 'wb') as fp:
                fp.write(file.getvalue())
            attach_response = upload_file_to_cyops(file_path=file_name, filename=file_name,
                                                   name=file_name, create_attachment=True)
            return attach_response

    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))

def remove_file_share(config, params, connector_info):
    try:
        service = _new_service(config, 'drive', 'v3', connector_info)
        file_id = params.get('file_id') or params.get('fileId')
        permission_id = params.get('permission_id') or params.get('permissionId')
        email_address = params.get('email_address') or params.get('emailAddress')

        if not file_id:
            raise ConnectorError('Missing required parameter: file_id')

        permissions_resp = service.permissions().list(
            fileId=file_id,
            fields='permissions(id,emailAddress,role,type)'
        ).execute()
        permissions = permissions_resp.get('permissions', [])

        if permission_id:
            target_permissions = [perm for perm in permissions if perm.get('id') == permission_id]
            if not target_permissions:
                raise ConnectorError('Permission ID not found for specified file')
        elif email_address:
            target_permissions = [
                perm for perm in permissions
                if (perm.get('emailAddress') or '').lower() == email_address.lower()
            ]
            if not target_permissions:
                raise ConnectorError('No shared permission found for specified email address')
        else:
            # If no target is specified, remove all non-owner permissions.
            target_permissions = [perm for perm in permissions if perm.get('role') != 'owner']

        removed_permission_ids = []
        for permission in target_permissions:
            perm_id = permission.get('id')
            if not perm_id or permission.get('role') == 'owner':
                continue
            service.permissions().delete(fileId=file_id, permissionId=perm_id).execute()
            removed_permission_ids.append(perm_id)

        return {
            'file_id': file_id,
            'removed_permissions': removed_permission_ids,
            'removed_count': len(removed_permission_ids)
        }
    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))

def _check_health(config, connector_info):
    try:
        return check(config, connector_info)
    except Exception as err:
        logger.exception("{0}".format(str(err)))
        raise ConnectorError("{0}".format(str(err)))


operations = {
    'get_all_files': get_all_files,
    'delete_file': delete_file,
    'empty_trash': empty_trash,
    'upload_file':upload_file,
    'download_file':download_file,
    'remove_file_share':remove_file_share
}
