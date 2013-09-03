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

from flask import Blueprint, render_template, request, g, current_app, Response, abort

import json

from geobox.model import ExternalWMTSSource, ExternalWFSSource
from geobox.lib.couchdb import CouchFileBox
from geobox.lib.tabular import geojson_to_rows, csv_export, ods_export
from geobox.web.forms import ExportVectorForm, WFSSearchForm
from .boxes import get_couch_box_db

editor_view = Blueprint('editor_view', __name__)

@editor_view.route('/editor')
def editor():
    export_form = ExportVectorForm(request.form)
    export_form.srs.choices = [(srs, srs) for srs in current_app.config.geobox_state.config.get('web', 'available_srs')]

    upload_box = current_app.config.geobox_state.config.get('couchdb', 'upload_box')
    export_form.destination.choices = [('file', 'Filesystem'), (upload_box, upload_box)]

    # load preview layer
    preview_features = False
    preview_layername = False

    box_name = request.args.get('box_name', False)
    filename = request.args.get('filename', False)
    if box_name and filename:
        couchbox = get_couch_box_db(box_name)
        couch_src = CouchFileBox('http://%s:%s' % ('127.0.0.1', current_app.config.geobox_state.config.get('couchdb', 'port')), couchbox)
        preview_features = couch_src.get_attachment(filename)
        preview_layername = "%s (temp)" % (filename)

    base_layer = g.db.query(ExternalWMTSSource).filter_by(background_layer=True).first()
    base_layer.bbox = base_layer.bbox_from_view_coverage()

    wfs_search_sources = g.db.query(ExternalWFSSource).filter_by(active=True).all()
    if not wfs_search_sources:
        wfs_search_sources = False
    wfs_search_form = WFSSearchForm(request.form)

    return render_template('editor.html',
        base_layer=base_layer,
        export_form=export_form,
        preview_layername=preview_layername,
        preview_features=preview_features,
        wfs_search_sources=wfs_search_sources,
        wfs_search_form=wfs_search_form,
        with_server=True,
    )

@editor_view.route('/editor/export/<export_type>', methods=['POST'])
def export_list(export_type='csv'):
    geojson =  request.form.get('data', False)
    headers = request.form.get('headers', False)

    if headers:
        headers = headers.split(',')
    if not geojson:
        abort(404)

    doc = json.loads(geojson)
    rows = geojson_to_rows(doc, headers=headers)

    if export_type == 'csv':
        filedata = csv_export(rows)
    else:
        filedata = ods_export(rows, with_headers=True)

    filename = "list.%s" % (export_type)

    return Response(filedata,
        headers={
            'Content-type': 'application/octet-stream',
            'Content-disposition': 'attachment; filename=%s' % filename
        }
    )


@editor_view.route('/editor-offline')
def editor_offline():
    return render_template('editor.html', with_server=False)
