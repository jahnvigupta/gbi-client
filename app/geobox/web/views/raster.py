# -:- encoding: utf-8 -:-
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

from flask import render_template, abort, flash, g, request, redirect, url_for, Blueprint, jsonify, current_app
from flaskext.babel import _
from ...model.sources import LocalWMTSSource

from geobox.model import ExternalWMTSSource, ExternalWFSSource
from geobox.web.forms import RasterSourceForm, WMSForm, UnlockRasterSourceForm
from geobox.lib.capabilities import parse_capabilities_url
from geobox.lib.coverage import llbbox_to_geojson
from geobox.lib.couchdb import VectorCouchDB

raster = Blueprint('raster', __name__)

@raster.route('/admin/raster/list', methods=["GET"])
def raster_list():
    external_sources = g.db.query(ExternalWMTSSource).filter_by(is_user_defined=False).filter_by(active=True).all()
    external_wfs_sources = g.db.query(ExternalWFSSource).filter_by(active=True).all()

    user_sources = g.db.query(ExternalWMTSSource).filter_by(is_user_defined=True).filter_by(background_layer=False).all()
    local_sources = g.db.query(LocalWMTSSource).all()
    return render_template('admin/external_raster_list.html', external_sources=external_sources,
        user_sources=user_sources, external_wfs_sources=external_wfs_sources, local_sources=local_sources)

@raster.route('/admin/<_type>/unlock/<int:id>', methods=["GET", "POST"])
def unlock_source(_type, id):
    if _type == 'wmts':
        source = g.db.query(ExternalWMTSSource).filter_by(id=id).first()
    elif _type == 'wfs':
        source = g.db.query(ExternalWFSSource).filter_by(id=id).first()

    form = UnlockRasterSourceForm(request.form, source)
    if form.validate_on_submit():
        source.username = form.data['username']
        source.password = form.data['password']
        flash( _('update WMTS'), 'success')
        g.db.commit()
        return redirect(url_for('.raster_list'))

    return render_template('admin/external_unlock.html', source=source, form=form)


@raster.route('/admin/wms/edit', methods=["GET", "POST"])
@raster.route('/admin/wms/edit/<int:id>', methods=["GET", "POST"])
def wms_edit(id=None):
    wms = g.db.query(ExternalWMTSSource).filter_by(id=id).first() if id else None
    if wms and not wms.is_user_defined:
        abort(404)

    edit_mode = True if wms  else False

    form = WMSForm(request.form, wms)
    if form.validate_on_submit():

        llbbox = form.data['llbbox']
        try:
            bbox_coverage = llbbox_to_geojson(llbbox)
        except ValueError:
            try:
                bbox_coverage = json.dumps(json.loads(llbbox))
            except ValueError:
                flash( _('invalid bbox'), 'error')
                return render_template('admin/external_wms.html', form=form, edit_mode=edit_mode)

        if not wms:
            wms = ExternalWMTSSource(
                name=form.data['name'],
                title=form.data['title'],
                url=form.data['url'],
                layer = form.data['layer'],
                format = form.data['format'],
                srs = form.data['srs'],
                username = form.data['username'],
                password = form.data['password'],
                prefix = 'local',
                is_user_defined=True,
                source_type='wms',
                download_level_start=0,
                download_level_end=20,
                active=True,
                download_coverage=bbox_coverage,
            )
            g.db.add(wms)
            flash( _('Save local WMS'), 'success')
        else:
            wms.name  = form.data['name']
            wms.title = form.data['title']
            wms.url = form.data['url']
            wms.layer = form.data['layer']
            wms.format = form.data['format']
            wms.version = form.data['version']
            wms.srs = form.data['srs']
            wms.username = form.data['username']
            wms.password = form.data['password']
            wms.prefix = 'local'
            wms.active = True
            wms.download_coverage = bbox_coverage
            flash( _('update WMS'), 'success')
        g.db.commit()
        return redirect(url_for('.raster_list'))
    if wms:
        form.llbbox.data = wms.download_coverage
    return render_template('admin/external_wms.html', form=form, edit_mode=edit_mode)

@raster.route('/admin/wms/capabilities', methods=["GET"])
def wms_capabilities():
    url = request.args.get('url', False)
    if not url:
        return jsonify(error=_('Need url for capabilities'))

    try:
        data = parse_capabilities_url(url)
    except:
        data = {'error': 'load capabilities not possible'}
    return jsonify(data=data)

@raster.route('/admin/wmts/edit', methods=["GET", "POST"])
@raster.route('/admin/wmts/edit/<int:id>', methods=["GET", "POST"])
def wmts_edit(id=None):
    wmts = g.db.query(ExternalWMTSSource).filter_by(id=id).first() if id else None
    if wmts and not wmts.is_user_defined:
        abort(404)

    form = RasterSourceForm(request.form, wmts)

    if form.validate_on_submit():
        llbbox = form.data['llbbox']
        try:
            bbox_coverage = llbbox_to_geojson(llbbox)
        except ValueError:
            try:
                bbox_coverage = json.dumps(json.loads(llbbox))
            except ValueError:
                flash( _('invalid bbox'), 'error')
                return render_template('admin/external_wmts.html', form=form)

        if not wmts:
            wmts = ExternalWMTSSource(
                name=form.data['name'],
                title=form.data['title'],
                url=form.data['url'],
                format=form.data['format'],
                username = form.data['username'],
                password = form.data['password'],
                is_user_defined= True,
                prefix = 'local',
                source_type='wmts',
                download_level_start=0,
                download_level_end=20,
                download_coverage = bbox_coverage,
                active=True,
            )
            g.db.add(wmts)
            flash( _('Save local WMTS'), 'success')
        else:
            wmts.name  = form.data['name']
            wmts.title = form.data['title']
            wmts.url = form.data['url']
            wmts.format = form.data['format']
            wmts.username = form.data['username']
            wmts.password = form.data['password']
            wmts.download_coverage = bbox_coverage
            wmts.prefix = 'local'
            flash( _('update WMTS'), 'success')
        g.db.commit()
        return redirect(url_for('.raster_list'))
    if wmts:
        form.llbbox.data = wmts.download_coverage
    return render_template('admin/external_wmts.html', form=form)

@raster.route('/admin/localraster/remove/<int:id>', methods=["GET", "POST"])
def local_raster_remove(id):
    raster_source = g.db.query(LocalWMTSSource).with_polymorphic('*').filter_by(id=id).first()

    if not raster_source:
        abort(404)

    couch_url = 'http://%s:%s' % ('127.0.0.1', current_app.config.geobox_state.config.get('couchdb', 'port'))
    couch = VectorCouchDB(couch_url, raster_source.name, raster_source.name)
    couch.delete_db()

    g.db.delete(raster_source)
    g.db.commit()
    flash( _('delete local source successful'), 'success')
    return redirect(url_for('.raster_list'))

@raster.route('/admin/raster/remove/<int:id>', methods=["GET", "POST"])
def raster_remove(id):
    raster_source = g.db.query(ExternalWMTSSource).with_polymorphic('*').filter_by(id=id).filter_by(is_user_defined=True).first()

    if not raster_source:
        abort(404)

    g.db.delete(raster_source)
    g.db.commit()
    flash( _('delete source successful'), 'success')
    return redirect(url_for('.raster_list'))
