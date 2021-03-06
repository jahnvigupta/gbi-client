# This file is part of the GBI project.
# Copyright (C) 2012 Omniscale GmbH & Co. KG <http://omniscale.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from tempfile import mkdtemp
from os import path
from shutil import rmtree

from geobox.process.base import ProcessBase
from geobox.lib.couchdb import VectorCouchDB, CouchFileBox
from geobox.lib.vectormapping import Mapping
from geobox.lib.vectorconvert import (
    load_json_from_shape, write_json_to_shape, fields_from_properties,
    write_json_to_file, create_feature_collection, ConvertError,
    zip_shapefiles, load_json_from_gml
)

import logging
log = logging.getLogger(__name__)


class VectorExportProcess(ProcessBase):
    def process(self):
        log.debug('Start vector export process. Task %d' % self.task_id)
        try:
            with self.task() as task:
                couch = VectorCouchDB('http://%s:%s' % ('127.0.0.1', self.app_state.config.get('couchdb', 'port')), task.db_name, task.title)

                if task.type_ == 'geojson':
                    # use geojson if is in task - otherwise load from database
                    if not task.geojson:
                        data = json.dumps(create_feature_collection(couch.load_features()))
                    else:
                        data = task.geojson

                    # check metadata for jsonSchema and restrict feature properties to
                    # schema properties of schema don't allow additional properties
                    metadata = couch.metadata()
                    if metadata and 'appOptions' in metadata and 'jsonSchema' in metadata['appOptions'] and 'additionalProperties' in metadata['appOptions']['jsonSchema']['schema'] and metadata['appOptions']['jsonSchema']['schema']['additionalProperties'] == False:
                        schema_properties = metadata['appOptions']['jsonSchema']['schema']['properties'].keys()
                        data = json.loads(data)
                        for feature in data['features']:
                            export_properties = {}
                            for key in feature['properties'].keys():
                                if key in schema_properties:
                                    export_properties[key] = feature['properties'][key]
                            feature['properties'] = export_properties
                        data = json.dumps(data)

                    if task.destination != 'file':
                        dest_couch = CouchFileBox('http://%s:%s' % ('127.0.0.1', self.app_state.config.get('couchdb', 'port')), task.destination)

                        file_obj = {'content-type': 'application/json' , 'file': data, 'filename': task.file_name + '.json' }
                        dest_couch.store_file(file_obj, overwrite=True)
                    else:
                        output_file = self.app_state.user_data_path('export', 'vector', task.file_name + '.json', make_dirs=True)
                        write_json_to_file(json.loads(data), output_file)

                elif task.type_ == 'shp':
                    if task.destination != 'file':
                        dest_couch = CouchFileBox('http://%s:%s' % ('127.0.0.1', self.app_state.config.get('couchdb', 'port')), task.destination)
                        temp_dir = mkdtemp()

                        output_file = path.join(temp_dir, task.file_name + '.shp')
                        fields = fields_from_properties(couch.load_features())
                        mapping = Mapping(None, None, 'Polygon', other_srs=task.srs, fields=fields)

                        # create shape
                        write_json_to_shape(couch.load_features(), mapping, output_file)
                        zip_file = zip_shapefiles(output_file)
                        dest_couch.store_file({'content-type': 'application/zip', 'file': zip_file.getvalue(), 'filename': task.file_name + '.zip' }, overwrite=True)

                        rmtree(temp_dir)
                    else:
                        output_file = self.app_state.user_data_path('export',  'vector', task.file_name+ '.shp', make_dirs=True)
                        # create fields for shp - use for mapping
                        fields = fields_from_properties(couch.load_features())
                        mapping = Mapping(None, None, 'Polygon', other_srs=task.srs, fields=fields)
                        # create shape
                        write_json_to_shape(couch.load_features(), mapping, output_file)
            self.task_done()
        except ConvertError, e:
            self.task_failed(e)
        except AssertionError, e:
            # fiona uses assertions without error messages
            if not str(e):
                self.task_failed(ConvertError('unable to write shapefile'))
            else:
                self.task_failed(e)
        except KeyError, e:
            # mapping not exists
            self.task_failed(e)
        except Exception, e:
            self.task_failed(e)


class VectorImportProcess(ProcessBase):
    def process(self):
        log.debug('Start vector import process. Task %d' % self.task_id)
        try:
            with self.task() as task:
                mapping = Mapping(None, None, '*', other_srs=task.srs)
                couch = VectorCouchDB('http://%s:%s' % ('127.0.0.1', self.app_state.config.get('couchdb', 'port')), task.db_name, task.title)
                # import from file
                if task.source == 'file':
                    input_file = self.app_state.user_data_path('import', task.file_name)
                    if task.type_ == 'geojson':
                        records = json.loads(open(input_file).read())
                        couch.store_records(
                            records['features']
                        )
                    elif task.type_ == 'gml':
                        couch.store_records(
                            load_json_from_gml(input_file, mapping)
                        )
                    elif task.type_ == 'shp':
                        couch.store_records(
                            load_json_from_shape(input_file, mapping)
                        )
                # import from couch db - source name is couchdb name
                else:
                    couch_src = CouchFileBox('http://%s:%s' % ('127.0.0.1', self.app_state.config.get('couchdb', 'port')), task.source)
                    records = couch_src.get_attachment(task.file_name)
                    couch.store_records(
                        records['features']
                    )
            self.task_done()
        except ConvertError, e:
            self.task_failed(e)
        except AssertionError, e:
            # fiona uses assertions without error messages
            if not str(e):
                self.task_failed(ConvertError('unable to read shapefile'))
            else:
                self.task_failed(e)
        except KeyError, e:
            # mapping not exists
            self.task_failed(e)
        except Exception, e:
            self.task_failed(e)
