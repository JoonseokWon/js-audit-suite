"""Explicit fast-forward public audit-only v1.9.0 release operations. No action on import.

Credentials come from the existing Git credential helper and stay in memory.
Git sends source files once through its normal pack protocol. Release assets
use the GitHub upload API; no per-source-file blob upload is performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / '검증' / 'v1.9.0' / 'github-release'
STATE = WORK / 'release-state.json'
CHECKOUT = WORK / 'checkout'
OWNER = 'JoonseokWon'
PREVIOUS_REPOSITORY = OWNER + '/for-ax-node-project'
REPOSITORY = OWNER + '/js-audit-suite'
SOURCE_PREFIX = 'js-audit-suite/'
BASE_COMMIT = 'd9d3c18459eddce6a01d51b9bafbce441782cc16'
PREVIOUS_TAG = 'v1.8.1'
PREVIOUS_RELEASES = {'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab',
                     'v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
                     'v1.8.0':'c47250b5c092010342462a6a63d23692fd062637',
                     'v1.8.1':BASE_COMMIT}
OLD_WORKFLOW_PATHS = ('.github/workflows/audit-suite-v17.yml',
                      '.github/workflows/audit-suite-v171.yml',
                      '.github/workflows/audit-suite-v18.yml',
                      '.github/workflows/audit-suite-v181.yml')
REMOTE = 'https://github.com/' + REPOSITORY + '.git'
TAG = 'v1.9.0'
BRANCH = 'main'
SOURCE_NAME = 'js-audit-suite-v1.9.0-source.zip'
DEFAULT_WINDOWS_NAME = 'JS-Audit-Suite-v1.9.0-windows.zip'
WINDOWS_PREFIX = 'JS-Audit-Suite-v1.9.0/'
PROOF_SCHEMA = 'audit-suite-v19-final-validation-1'
SUPPORTED_SCOPE = '설계상서식참고연결+계획/위험/증거기계적검증+HITL·잠금/취합'
BASELINE_PATHS = frozenset((
    '.gitattributes',
    '.runtime/tcl_library/auto.tcl',
    '.runtime/tcl_library/clock.tcl',
    '.runtime/tcl_library/cookiejar/cookiejar.tcl',
    '.runtime/tcl_library/cookiejar/idna.tcl',
    '.runtime/tcl_library/cookiejar/pkgIndex.tcl',
    '.runtime/tcl_library/cookiejar/public_suffix_list.dat.gz',
    '.runtime/tcl_library/encoding/ascii.enc',
    '.runtime/tcl_library/encoding/big5.enc',
    '.runtime/tcl_library/encoding/cns11643.enc',
    '.runtime/tcl_library/encoding/cp1250.enc',
    '.runtime/tcl_library/encoding/cp1251.enc',
    '.runtime/tcl_library/encoding/cp1252.enc',
    '.runtime/tcl_library/encoding/cp1253.enc',
    '.runtime/tcl_library/encoding/cp1254.enc',
    '.runtime/tcl_library/encoding/cp1255.enc',
    '.runtime/tcl_library/encoding/cp1256.enc',
    '.runtime/tcl_library/encoding/cp1257.enc',
    '.runtime/tcl_library/encoding/cp1258.enc',
    '.runtime/tcl_library/encoding/cp165.enc',
    '.runtime/tcl_library/encoding/cp437.enc',
    '.runtime/tcl_library/encoding/cp737.enc',
    '.runtime/tcl_library/encoding/cp775.enc',
    '.runtime/tcl_library/encoding/cp850.enc',
    '.runtime/tcl_library/encoding/cp852.enc',
    '.runtime/tcl_library/encoding/cp855.enc',
    '.runtime/tcl_library/encoding/cp857.enc',
    '.runtime/tcl_library/encoding/cp860.enc',
    '.runtime/tcl_library/encoding/cp861.enc',
    '.runtime/tcl_library/encoding/cp862.enc',
    '.runtime/tcl_library/encoding/cp863.enc',
    '.runtime/tcl_library/encoding/cp864.enc',
    '.runtime/tcl_library/encoding/cp865.enc',
    '.runtime/tcl_library/encoding/cp866.enc',
    '.runtime/tcl_library/encoding/cp869.enc',
    '.runtime/tcl_library/encoding/cp874.enc',
    '.runtime/tcl_library/encoding/cp932.enc',
    '.runtime/tcl_library/encoding/cp936.enc',
    '.runtime/tcl_library/encoding/cp949.enc',
    '.runtime/tcl_library/encoding/cp950.enc',
    '.runtime/tcl_library/encoding/dingbats.enc',
    '.runtime/tcl_library/encoding/ebcdic.enc',
    '.runtime/tcl_library/encoding/euc-cn.enc',
    '.runtime/tcl_library/encoding/euc-jp.enc',
    '.runtime/tcl_library/encoding/euc-kr.enc',
    '.runtime/tcl_library/encoding/gb12345.enc',
    '.runtime/tcl_library/encoding/gb1988.enc',
    '.runtime/tcl_library/encoding/gb2312-raw.enc',
    '.runtime/tcl_library/encoding/gb2312.enc',
    '.runtime/tcl_library/encoding/iso2022-jp.enc',
    '.runtime/tcl_library/encoding/iso2022-kr.enc',
    '.runtime/tcl_library/encoding/iso2022.enc',
    '.runtime/tcl_library/encoding/iso8859-1.enc',
    '.runtime/tcl_library/encoding/iso8859-10.enc',
    '.runtime/tcl_library/encoding/iso8859-11.enc',
    '.runtime/tcl_library/encoding/iso8859-13.enc',
    '.runtime/tcl_library/encoding/iso8859-14.enc',
    '.runtime/tcl_library/encoding/iso8859-15.enc',
    '.runtime/tcl_library/encoding/iso8859-16.enc',
    '.runtime/tcl_library/encoding/iso8859-2.enc',
    '.runtime/tcl_library/encoding/iso8859-3.enc',
    '.runtime/tcl_library/encoding/iso8859-4.enc',
    '.runtime/tcl_library/encoding/iso8859-5.enc',
    '.runtime/tcl_library/encoding/iso8859-6.enc',
    '.runtime/tcl_library/encoding/iso8859-7.enc',
    '.runtime/tcl_library/encoding/iso8859-8.enc',
    '.runtime/tcl_library/encoding/iso8859-9.enc',
    '.runtime/tcl_library/encoding/jis0201.enc',
    '.runtime/tcl_library/encoding/jis0208.enc',
    '.runtime/tcl_library/encoding/jis0212.enc',
    '.runtime/tcl_library/encoding/koi8-r.enc',
    '.runtime/tcl_library/encoding/koi8-ru.enc',
    '.runtime/tcl_library/encoding/koi8-t.enc',
    '.runtime/tcl_library/encoding/koi8-u.enc',
    '.runtime/tcl_library/encoding/ksc5601.enc',
    '.runtime/tcl_library/encoding/macCentEuro.enc',
    '.runtime/tcl_library/encoding/macCroatian.enc',
    '.runtime/tcl_library/encoding/macCyrillic.enc',
    '.runtime/tcl_library/encoding/macDingbats.enc',
    '.runtime/tcl_library/encoding/macGreek.enc',
    '.runtime/tcl_library/encoding/macIceland.enc',
    '.runtime/tcl_library/encoding/macJapan.enc',
    '.runtime/tcl_library/encoding/macRoman.enc',
    '.runtime/tcl_library/encoding/macRomania.enc',
    '.runtime/tcl_library/encoding/macThai.enc',
    '.runtime/tcl_library/encoding/macTurkish.enc',
    '.runtime/tcl_library/encoding/macUkraine.enc',
    '.runtime/tcl_library/encoding/shiftjis.enc',
    '.runtime/tcl_library/encoding/symbol.enc',
    '.runtime/tcl_library/encoding/tis-620.enc',
    '.runtime/tcl_library/foreachline.tcl',
    '.runtime/tcl_library/history.tcl',
    '.runtime/tcl_library/http/http.tcl',
    '.runtime/tcl_library/http/pkgIndex.tcl',
    '.runtime/tcl_library/icu.tcl',
    '.runtime/tcl_library/init.tcl',
    '.runtime/tcl_library/install.tcl',
    '.runtime/tcl_library/license.terms',
    '.runtime/tcl_library/msgcat/msgcat.tcl',
    '.runtime/tcl_library/msgcat/pkgIndex.tcl',
    '.runtime/tcl_library/msgs/af.msg',
    '.runtime/tcl_library/msgs/af_za.msg',
    '.runtime/tcl_library/msgs/ar.msg',
    '.runtime/tcl_library/msgs/ar_in.msg',
    '.runtime/tcl_library/msgs/ar_jo.msg',
    '.runtime/tcl_library/msgs/ar_lb.msg',
    '.runtime/tcl_library/msgs/ar_sy.msg',
    '.runtime/tcl_library/msgs/be.msg',
    '.runtime/tcl_library/msgs/bg.msg',
    '.runtime/tcl_library/msgs/bn.msg',
    '.runtime/tcl_library/msgs/bn_in.msg',
    '.runtime/tcl_library/msgs/ca.msg',
    '.runtime/tcl_library/msgs/cs.msg',
    '.runtime/tcl_library/msgs/da.msg',
    '.runtime/tcl_library/msgs/de.msg',
    '.runtime/tcl_library/msgs/de_at.msg',
    '.runtime/tcl_library/msgs/de_be.msg',
    '.runtime/tcl_library/msgs/el.msg',
    '.runtime/tcl_library/msgs/en_au.msg',
    '.runtime/tcl_library/msgs/en_be.msg',
    '.runtime/tcl_library/msgs/en_bw.msg',
    '.runtime/tcl_library/msgs/en_ca.msg',
    '.runtime/tcl_library/msgs/en_gb.msg',
    '.runtime/tcl_library/msgs/en_hk.msg',
    '.runtime/tcl_library/msgs/en_ie.msg',
    '.runtime/tcl_library/msgs/en_in.msg',
    '.runtime/tcl_library/msgs/en_nz.msg',
    '.runtime/tcl_library/msgs/en_ph.msg',
    '.runtime/tcl_library/msgs/en_sg.msg',
    '.runtime/tcl_library/msgs/en_za.msg',
    '.runtime/tcl_library/msgs/en_zw.msg',
    '.runtime/tcl_library/msgs/eo.msg',
    '.runtime/tcl_library/msgs/es.msg',
    '.runtime/tcl_library/msgs/es_ar.msg',
    '.runtime/tcl_library/msgs/es_bo.msg',
    '.runtime/tcl_library/msgs/es_cl.msg',
    '.runtime/tcl_library/msgs/es_co.msg',
    '.runtime/tcl_library/msgs/es_cr.msg',
    '.runtime/tcl_library/msgs/es_do.msg',
    '.runtime/tcl_library/msgs/es_ec.msg',
    '.runtime/tcl_library/msgs/es_gt.msg',
    '.runtime/tcl_library/msgs/es_hn.msg',
    '.runtime/tcl_library/msgs/es_mx.msg',
    '.runtime/tcl_library/msgs/es_ni.msg',
    '.runtime/tcl_library/msgs/es_pa.msg',
    '.runtime/tcl_library/msgs/es_pe.msg',
    '.runtime/tcl_library/msgs/es_pr.msg',
    '.runtime/tcl_library/msgs/es_py.msg',
    '.runtime/tcl_library/msgs/es_sv.msg',
    '.runtime/tcl_library/msgs/es_uy.msg',
    '.runtime/tcl_library/msgs/es_ve.msg',
    '.runtime/tcl_library/msgs/et.msg',
    '.runtime/tcl_library/msgs/eu.msg',
    '.runtime/tcl_library/msgs/eu_es.msg',
    '.runtime/tcl_library/msgs/fa.msg',
    '.runtime/tcl_library/msgs/fa_in.msg',
    '.runtime/tcl_library/msgs/fa_ir.msg',
    '.runtime/tcl_library/msgs/fi.msg',
    '.runtime/tcl_library/msgs/fo.msg',
    '.runtime/tcl_library/msgs/fo_fo.msg',
    '.runtime/tcl_library/msgs/fr.msg',
    '.runtime/tcl_library/msgs/fr_be.msg',
    '.runtime/tcl_library/msgs/fr_ca.msg',
    '.runtime/tcl_library/msgs/fr_ch.msg',
    '.runtime/tcl_library/msgs/ga.msg',
    '.runtime/tcl_library/msgs/ga_ie.msg',
    '.runtime/tcl_library/msgs/gl.msg',
    '.runtime/tcl_library/msgs/gl_es.msg',
    '.runtime/tcl_library/msgs/gv.msg',
    '.runtime/tcl_library/msgs/gv_gb.msg',
    '.runtime/tcl_library/msgs/he.msg',
    '.runtime/tcl_library/msgs/hi.msg',
    '.runtime/tcl_library/msgs/hi_in.msg',
    '.runtime/tcl_library/msgs/hr.msg',
    '.runtime/tcl_library/msgs/hu.msg',
    '.runtime/tcl_library/msgs/id.msg',
    '.runtime/tcl_library/msgs/id_id.msg',
    '.runtime/tcl_library/msgs/is.msg',
    '.runtime/tcl_library/msgs/it.msg',
    '.runtime/tcl_library/msgs/it_ch.msg',
    '.runtime/tcl_library/msgs/ja.msg',
    '.runtime/tcl_library/msgs/kl.msg',
    '.runtime/tcl_library/msgs/kl_gl.msg',
    '.runtime/tcl_library/msgs/ko.msg',
    '.runtime/tcl_library/msgs/ko_kr.msg',
    '.runtime/tcl_library/msgs/kok.msg',
    '.runtime/tcl_library/msgs/kok_in.msg',
    '.runtime/tcl_library/msgs/kw.msg',
    '.runtime/tcl_library/msgs/kw_gb.msg',
    '.runtime/tcl_library/msgs/lt.msg',
    '.runtime/tcl_library/msgs/lv.msg',
    '.runtime/tcl_library/msgs/mk.msg',
    '.runtime/tcl_library/msgs/mr.msg',
    '.runtime/tcl_library/msgs/mr_in.msg',
    '.runtime/tcl_library/msgs/ms.msg',
    '.runtime/tcl_library/msgs/ms_my.msg',
    '.runtime/tcl_library/msgs/mt.msg',
    '.runtime/tcl_library/msgs/nb.msg',
    '.runtime/tcl_library/msgs/nl.msg',
    '.runtime/tcl_library/msgs/nl_be.msg',
    '.runtime/tcl_library/msgs/nn.msg',
    '.runtime/tcl_library/msgs/pl.msg',
    '.runtime/tcl_library/msgs/pt.msg',
    '.runtime/tcl_library/msgs/pt_br.msg',
    '.runtime/tcl_library/msgs/ro.msg',
    '.runtime/tcl_library/msgs/ru.msg',
    '.runtime/tcl_library/msgs/ru_ua.msg',
    '.runtime/tcl_library/msgs/sh.msg',
    '.runtime/tcl_library/msgs/sk.msg',
    '.runtime/tcl_library/msgs/sl.msg',
    '.runtime/tcl_library/msgs/sq.msg',
    '.runtime/tcl_library/msgs/sr.msg',
    '.runtime/tcl_library/msgs/sv.msg',
    '.runtime/tcl_library/msgs/sw.msg',
    '.runtime/tcl_library/msgs/ta.msg',
    '.runtime/tcl_library/msgs/ta_in.msg',
    '.runtime/tcl_library/msgs/te.msg',
    '.runtime/tcl_library/msgs/te_in.msg',
    '.runtime/tcl_library/msgs/th.msg',
    '.runtime/tcl_library/msgs/tr.msg',
    '.runtime/tcl_library/msgs/uk.msg',
    '.runtime/tcl_library/msgs/vi.msg',
    '.runtime/tcl_library/msgs/zh.msg',
    '.runtime/tcl_library/msgs/zh_cn.msg',
    '.runtime/tcl_library/msgs/zh_hk.msg',
    '.runtime/tcl_library/msgs/zh_sg.msg',
    '.runtime/tcl_library/msgs/zh_tw.msg',
    '.runtime/tcl_library/opt/optparse.tcl',
    '.runtime/tcl_library/opt/pkgIndex.tcl',
    '.runtime/tcl_library/package.tcl',
    '.runtime/tcl_library/parray.tcl',
    '.runtime/tcl_library/pkgIndex.tcl',
    '.runtime/tcl_library/platform/pkgIndex.tcl',
    '.runtime/tcl_library/platform/platform.tcl',
    '.runtime/tcl_library/platform/shell.tcl',
    '.runtime/tcl_library/readfile.tcl',
    '.runtime/tcl_library/safe.tcl',
    '.runtime/tcl_library/tclIndex',
    '.runtime/tcl_library/tcltest/pkgIndex.tcl',
    '.runtime/tcl_library/tcltest/tcltest.tcl',
    '.runtime/tcl_library/tm.tcl',
    '.runtime/tcl_library/tzdata/Africa/Abidjan',
    '.runtime/tcl_library/tzdata/Africa/Accra',
    '.runtime/tcl_library/tzdata/Africa/Addis_Ababa',
    '.runtime/tcl_library/tzdata/Africa/Algiers',
    '.runtime/tcl_library/tzdata/Africa/Asmara',
    '.runtime/tcl_library/tzdata/Africa/Asmera',
    '.runtime/tcl_library/tzdata/Africa/Bamako',
    '.runtime/tcl_library/tzdata/Africa/Bangui',
    '.runtime/tcl_library/tzdata/Africa/Banjul',
    '.runtime/tcl_library/tzdata/Africa/Bissau',
    '.runtime/tcl_library/tzdata/Africa/Blantyre',
    '.runtime/tcl_library/tzdata/Africa/Brazzaville',
    '.runtime/tcl_library/tzdata/Africa/Bujumbura',
    '.runtime/tcl_library/tzdata/Africa/Cairo',
    '.runtime/tcl_library/tzdata/Africa/Casablanca',
    '.runtime/tcl_library/tzdata/Africa/Ceuta',
    '.runtime/tcl_library/tzdata/Africa/Conakry',
    '.runtime/tcl_library/tzdata/Africa/Dakar',
    '.runtime/tcl_library/tzdata/Africa/Dar_es_Salaam',
    '.runtime/tcl_library/tzdata/Africa/Djibouti',
    '.runtime/tcl_library/tzdata/Africa/Douala',
    '.runtime/tcl_library/tzdata/Africa/El_Aaiun',
    '.runtime/tcl_library/tzdata/Africa/Freetown',
    '.runtime/tcl_library/tzdata/Africa/Gaborone',
    '.runtime/tcl_library/tzdata/Africa/Harare',
    '.runtime/tcl_library/tzdata/Africa/Johannesburg',
    '.runtime/tcl_library/tzdata/Africa/Juba',
    '.runtime/tcl_library/tzdata/Africa/Kampala',
    '.runtime/tcl_library/tzdata/Africa/Khartoum',
    '.runtime/tcl_library/tzdata/Africa/Kigali',
    '.runtime/tcl_library/tzdata/Africa/Kinshasa',
    '.runtime/tcl_library/tzdata/Africa/Lagos',
    '.runtime/tcl_library/tzdata/Africa/Libreville',
    '.runtime/tcl_library/tzdata/Africa/Lome',
    '.runtime/tcl_library/tzdata/Africa/Luanda',
    '.runtime/tcl_library/tzdata/Africa/Lubumbashi',
    '.runtime/tcl_library/tzdata/Africa/Lusaka',
    '.runtime/tcl_library/tzdata/Africa/Malabo',
    '.runtime/tcl_library/tzdata/Africa/Maputo',
    '.runtime/tcl_library/tzdata/Africa/Maseru',
    '.runtime/tcl_library/tzdata/Africa/Mbabane',
    '.runtime/tcl_library/tzdata/Africa/Mogadishu',
    '.runtime/tcl_library/tzdata/Africa/Monrovia',
    '.runtime/tcl_library/tzdata/Africa/Nairobi',
    '.runtime/tcl_library/tzdata/Africa/Ndjamena',
    '.runtime/tcl_library/tzdata/Africa/Niamey',
    '.runtime/tcl_library/tzdata/Africa/Nouakchott',
    '.runtime/tcl_library/tzdata/Africa/Ouagadougou',
    '.runtime/tcl_library/tzdata/Africa/Porto-Novo',
    '.runtime/tcl_library/tzdata/Africa/Sao_Tome',
    '.runtime/tcl_library/tzdata/Africa/Timbuktu',
    '.runtime/tcl_library/tzdata/Africa/Tripoli',
    '.runtime/tcl_library/tzdata/Africa/Tunis',
    '.runtime/tcl_library/tzdata/Africa/Windhoek',
    '.runtime/tcl_library/tzdata/America/Adak',
    '.runtime/tcl_library/tzdata/America/Anchorage',
    '.runtime/tcl_library/tzdata/America/Anguilla',
    '.runtime/tcl_library/tzdata/America/Antigua',
    '.runtime/tcl_library/tzdata/America/Araguaina',
    '.runtime/tcl_library/tzdata/America/Argentina/Buenos_Aires',
    '.runtime/tcl_library/tzdata/America/Argentina/Catamarca',
    '.runtime/tcl_library/tzdata/America/Argentina/ComodRivadavia',
    '.runtime/tcl_library/tzdata/America/Argentina/Cordoba',
    '.runtime/tcl_library/tzdata/America/Argentina/Jujuy',
    '.runtime/tcl_library/tzdata/America/Argentina/La_Rioja',
    '.runtime/tcl_library/tzdata/America/Argentina/Mendoza',
    '.runtime/tcl_library/tzdata/America/Argentina/Rio_Gallegos',
    '.runtime/tcl_library/tzdata/America/Argentina/Salta',
    '.runtime/tcl_library/tzdata/America/Argentina/San_Juan',
    '.runtime/tcl_library/tzdata/America/Argentina/San_Luis',
    '.runtime/tcl_library/tzdata/America/Argentina/Tucuman',
    '.runtime/tcl_library/tzdata/America/Argentina/Ushuaia',
    '.runtime/tcl_library/tzdata/America/Aruba',
    '.runtime/tcl_library/tzdata/America/Asuncion',
    '.runtime/tcl_library/tzdata/America/Atikokan',
    '.runtime/tcl_library/tzdata/America/Atka',
    '.runtime/tcl_library/tzdata/America/Bahia',
    '.runtime/tcl_library/tzdata/America/Bahia_Banderas',
    '.runtime/tcl_library/tzdata/America/Barbados',
    '.runtime/tcl_library/tzdata/America/Belem',
    '.runtime/tcl_library/tzdata/America/Belize',
    '.runtime/tcl_library/tzdata/America/Blanc-Sablon',
    '.runtime/tcl_library/tzdata/America/Boa_Vista',
    '.runtime/tcl_library/tzdata/America/Bogota',
    '.runtime/tcl_library/tzdata/America/Boise',
    '.runtime/tcl_library/tzdata/America/Buenos_Aires',
    '.runtime/tcl_library/tzdata/America/Cambridge_Bay',
    '.runtime/tcl_library/tzdata/America/Campo_Grande',
    '.runtime/tcl_library/tzdata/America/Cancun',
    '.runtime/tcl_library/tzdata/America/Caracas',
    '.runtime/tcl_library/tzdata/America/Catamarca',
    '.runtime/tcl_library/tzdata/America/Cayenne',
    '.runtime/tcl_library/tzdata/America/Cayman',
    '.runtime/tcl_library/tzdata/America/Chicago',
    '.runtime/tcl_library/tzdata/America/Chihuahua',
    '.runtime/tcl_library/tzdata/America/Ciudad_Juarez',
    '.runtime/tcl_library/tzdata/America/Coral_Harbour',
    '.runtime/tcl_library/tzdata/America/Cordoba',
    '.runtime/tcl_library/tzdata/America/Costa_Rica',
    '.runtime/tcl_library/tzdata/America/Coyhaique',
    '.runtime/tcl_library/tzdata/America/Creston',
    '.runtime/tcl_library/tzdata/America/Cuiaba',
    '.runtime/tcl_library/tzdata/America/Curacao',
    '.runtime/tcl_library/tzdata/America/Danmarkshavn',
    '.runtime/tcl_library/tzdata/America/Dawson',
    '.runtime/tcl_library/tzdata/America/Dawson_Creek',
    '.runtime/tcl_library/tzdata/America/Denver',
    '.runtime/tcl_library/tzdata/America/Detroit',
    '.runtime/tcl_library/tzdata/America/Dominica',
    '.runtime/tcl_library/tzdata/America/Edmonton',
    '.runtime/tcl_library/tzdata/America/Eirunepe',
    '.runtime/tcl_library/tzdata/America/El_Salvador',
    '.runtime/tcl_library/tzdata/America/Ensenada',
    '.runtime/tcl_library/tzdata/America/Fort_Nelson',
    '.runtime/tcl_library/tzdata/America/Fort_Wayne',
    '.runtime/tcl_library/tzdata/America/Fortaleza',
    '.runtime/tcl_library/tzdata/America/Glace_Bay',
    '.runtime/tcl_library/tzdata/America/Godthab',
    '.runtime/tcl_library/tzdata/America/Goose_Bay',
    '.runtime/tcl_library/tzdata/America/Grand_Turk',
    '.runtime/tcl_library/tzdata/America/Grenada',
    '.runtime/tcl_library/tzdata/America/Guadeloupe',
    '.runtime/tcl_library/tzdata/America/Guatemala',
    '.runtime/tcl_library/tzdata/America/Guayaquil',
    '.runtime/tcl_library/tzdata/America/Guyana',
    '.runtime/tcl_library/tzdata/America/Halifax',
    '.runtime/tcl_library/tzdata/America/Havana',
    '.runtime/tcl_library/tzdata/America/Hermosillo',
    '.runtime/tcl_library/tzdata/America/Indiana/Indianapolis',
    '.runtime/tcl_library/tzdata/America/Indiana/Knox',
    '.runtime/tcl_library/tzdata/America/Indiana/Marengo',
    '.runtime/tcl_library/tzdata/America/Indiana/Petersburg',
    '.runtime/tcl_library/tzdata/America/Indiana/Tell_City',
    '.runtime/tcl_library/tzdata/America/Indiana/Vevay',
    '.runtime/tcl_library/tzdata/America/Indiana/Vincennes',
    '.runtime/tcl_library/tzdata/America/Indiana/Winamac',
    '.runtime/tcl_library/tzdata/America/Indianapolis',
    '.runtime/tcl_library/tzdata/America/Inuvik',
    '.runtime/tcl_library/tzdata/America/Iqaluit',
    '.runtime/tcl_library/tzdata/America/Jamaica',
    '.runtime/tcl_library/tzdata/America/Jujuy',
    '.runtime/tcl_library/tzdata/America/Juneau',
    '.runtime/tcl_library/tzdata/America/Kentucky/Louisville',
    '.runtime/tcl_library/tzdata/America/Kentucky/Monticello',
    '.runtime/tcl_library/tzdata/America/Knox_IN',
    '.runtime/tcl_library/tzdata/America/Kralendijk',
    '.runtime/tcl_library/tzdata/America/La_Paz',
    '.runtime/tcl_library/tzdata/America/Lima',
    '.runtime/tcl_library/tzdata/America/Los_Angeles',
    '.runtime/tcl_library/tzdata/America/Louisville',
    '.runtime/tcl_library/tzdata/America/Lower_Princes',
    '.runtime/tcl_library/tzdata/America/Maceio',
    '.runtime/tcl_library/tzdata/America/Managua',
    '.runtime/tcl_library/tzdata/America/Manaus',
    '.runtime/tcl_library/tzdata/America/Marigot',
    '.runtime/tcl_library/tzdata/America/Martinique',
    '.runtime/tcl_library/tzdata/America/Matamoros',
    '.runtime/tcl_library/tzdata/America/Mazatlan',
    '.runtime/tcl_library/tzdata/America/Mendoza',
    '.runtime/tcl_library/tzdata/America/Menominee',
    '.runtime/tcl_library/tzdata/America/Merida',
    '.runtime/tcl_library/tzdata/America/Metlakatla',
    '.runtime/tcl_library/tzdata/America/Mexico_City',
    '.runtime/tcl_library/tzdata/America/Miquelon',
    '.runtime/tcl_library/tzdata/America/Moncton',
    '.runtime/tcl_library/tzdata/America/Monterrey',
    '.runtime/tcl_library/tzdata/America/Montevideo',
    '.runtime/tcl_library/tzdata/America/Montreal',
    '.runtime/tcl_library/tzdata/America/Montserrat',
    '.runtime/tcl_library/tzdata/America/Nassau',
    '.runtime/tcl_library/tzdata/America/New_York',
    '.runtime/tcl_library/tzdata/America/Nipigon',
    '.runtime/tcl_library/tzdata/America/Nome',
    '.runtime/tcl_library/tzdata/America/Noronha',
    '.runtime/tcl_library/tzdata/America/North_Dakota/Beulah',
    '.runtime/tcl_library/tzdata/America/North_Dakota/Center',
    '.runtime/tcl_library/tzdata/America/North_Dakota/New_Salem',
    '.runtime/tcl_library/tzdata/America/Nuuk',
    '.runtime/tcl_library/tzdata/America/Ojinaga',
    '.runtime/tcl_library/tzdata/America/Panama',
    '.runtime/tcl_library/tzdata/America/Pangnirtung',
    '.runtime/tcl_library/tzdata/America/Paramaribo',
    '.runtime/tcl_library/tzdata/America/Phoenix',
    '.runtime/tcl_library/tzdata/America/Port-au-Prince',
    '.runtime/tcl_library/tzdata/America/Port_of_Spain',
    '.runtime/tcl_library/tzdata/America/Porto_Acre',
    '.runtime/tcl_library/tzdata/America/Porto_Velho',
    '.runtime/tcl_library/tzdata/America/Puerto_Rico',
    '.runtime/tcl_library/tzdata/America/Punta_Arenas',
    '.runtime/tcl_library/tzdata/America/Rainy_River',
    '.runtime/tcl_library/tzdata/America/Rankin_Inlet',
    '.runtime/tcl_library/tzdata/America/Recife',
    '.runtime/tcl_library/tzdata/America/Regina',
    '.runtime/tcl_library/tzdata/America/Resolute',
    '.runtime/tcl_library/tzdata/America/Rio_Branco',
    '.runtime/tcl_library/tzdata/America/Rosario',
    '.runtime/tcl_library/tzdata/America/Santa_Isabel',
    '.runtime/tcl_library/tzdata/America/Santarem',
    '.runtime/tcl_library/tzdata/America/Santiago',
    '.runtime/tcl_library/tzdata/America/Santo_Domingo',
    '.runtime/tcl_library/tzdata/America/Sao_Paulo',
    '.runtime/tcl_library/tzdata/America/Scoresbysund',
    '.runtime/tcl_library/tzdata/America/Shiprock',
    '.runtime/tcl_library/tzdata/America/Sitka',
    '.runtime/tcl_library/tzdata/America/St_Barthelemy',
    '.runtime/tcl_library/tzdata/America/St_Johns',
    '.runtime/tcl_library/tzdata/America/St_Kitts',
    '.runtime/tcl_library/tzdata/America/St_Lucia',
    '.runtime/tcl_library/tzdata/America/St_Thomas',
    '.runtime/tcl_library/tzdata/America/St_Vincent',
    '.runtime/tcl_library/tzdata/America/Swift_Current',
    '.runtime/tcl_library/tzdata/America/Tegucigalpa',
    '.runtime/tcl_library/tzdata/America/Thule',
    '.runtime/tcl_library/tzdata/America/Thunder_Bay',
    '.runtime/tcl_library/tzdata/America/Tijuana',
    '.runtime/tcl_library/tzdata/America/Toronto',
    '.runtime/tcl_library/tzdata/America/Tortola',
    '.runtime/tcl_library/tzdata/America/Vancouver',
    '.runtime/tcl_library/tzdata/America/Virgin',
    '.runtime/tcl_library/tzdata/America/Whitehorse',
    '.runtime/tcl_library/tzdata/America/Winnipeg',
    '.runtime/tcl_library/tzdata/America/Yakutat',
    '.runtime/tcl_library/tzdata/America/Yellowknife',
    '.runtime/tcl_library/tzdata/Antarctica/Casey',
    '.runtime/tcl_library/tzdata/Antarctica/Davis',
    '.runtime/tcl_library/tzdata/Antarctica/DumontDUrville',
    '.runtime/tcl_library/tzdata/Antarctica/Macquarie',
    '.runtime/tcl_library/tzdata/Antarctica/Mawson',
    '.runtime/tcl_library/tzdata/Antarctica/McMurdo',
    '.runtime/tcl_library/tzdata/Antarctica/Palmer',
    '.runtime/tcl_library/tzdata/Antarctica/Rothera',
    '.runtime/tcl_library/tzdata/Antarctica/South_Pole',
    '.runtime/tcl_library/tzdata/Antarctica/Syowa',
    '.runtime/tcl_library/tzdata/Antarctica/Troll',
    '.runtime/tcl_library/tzdata/Antarctica/Vostok',
    '.runtime/tcl_library/tzdata/Arctic/Longyearbyen',
    '.runtime/tcl_library/tzdata/Asia/Aden',
    '.runtime/tcl_library/tzdata/Asia/Almaty',
    '.runtime/tcl_library/tzdata/Asia/Amman',
    '.runtime/tcl_library/tzdata/Asia/Anadyr',
    '.runtime/tcl_library/tzdata/Asia/Aqtau',
    '.runtime/tcl_library/tzdata/Asia/Aqtobe',
    '.runtime/tcl_library/tzdata/Asia/Ashgabat',
    '.runtime/tcl_library/tzdata/Asia/Ashkhabad',
    '.runtime/tcl_library/tzdata/Asia/Atyrau',
    '.runtime/tcl_library/tzdata/Asia/Baghdad',
    '.runtime/tcl_library/tzdata/Asia/Bahrain',
    '.runtime/tcl_library/tzdata/Asia/Baku',
    '.runtime/tcl_library/tzdata/Asia/Bangkok',
    '.runtime/tcl_library/tzdata/Asia/Barnaul',
    '.runtime/tcl_library/tzdata/Asia/Beirut',
    '.runtime/tcl_library/tzdata/Asia/Bishkek',
    '.runtime/tcl_library/tzdata/Asia/Brunei',
    '.runtime/tcl_library/tzdata/Asia/Calcutta',
    '.runtime/tcl_library/tzdata/Asia/Chita',
    '.runtime/tcl_library/tzdata/Asia/Choibalsan',
    '.runtime/tcl_library/tzdata/Asia/Chongqing',
    '.runtime/tcl_library/tzdata/Asia/Chungking',
    '.runtime/tcl_library/tzdata/Asia/Colombo',
    '.runtime/tcl_library/tzdata/Asia/Dacca',
    '.runtime/tcl_library/tzdata/Asia/Damascus',
    '.runtime/tcl_library/tzdata/Asia/Dhaka',
    '.runtime/tcl_library/tzdata/Asia/Dili',
    '.runtime/tcl_library/tzdata/Asia/Dubai',
    '.runtime/tcl_library/tzdata/Asia/Dushanbe',
    '.runtime/tcl_library/tzdata/Asia/Famagusta',
    '.runtime/tcl_library/tzdata/Asia/Gaza',
    '.runtime/tcl_library/tzdata/Asia/Harbin',
    '.runtime/tcl_library/tzdata/Asia/Hebron',
    '.runtime/tcl_library/tzdata/Asia/Ho_Chi_Minh',
    '.runtime/tcl_library/tzdata/Asia/Hong_Kong',
    '.runtime/tcl_library/tzdata/Asia/Hovd',
    '.runtime/tcl_library/tzdata/Asia/Irkutsk',
    '.runtime/tcl_library/tzdata/Asia/Istanbul',
    '.runtime/tcl_library/tzdata/Asia/Jakarta',
    '.runtime/tcl_library/tzdata/Asia/Jayapura',
    '.runtime/tcl_library/tzdata/Asia/Jerusalem',
    '.runtime/tcl_library/tzdata/Asia/Kabul',
    '.runtime/tcl_library/tzdata/Asia/Kamchatka',
    '.runtime/tcl_library/tzdata/Asia/Karachi',
    '.runtime/tcl_library/tzdata/Asia/Kashgar',
    '.runtime/tcl_library/tzdata/Asia/Kathmandu',
    '.runtime/tcl_library/tzdata/Asia/Katmandu',
    '.runtime/tcl_library/tzdata/Asia/Khandyga',
    '.runtime/tcl_library/tzdata/Asia/Kolkata',
    '.runtime/tcl_library/tzdata/Asia/Krasnoyarsk',
    '.runtime/tcl_library/tzdata/Asia/Kuala_Lumpur',
    '.runtime/tcl_library/tzdata/Asia/Kuching',
    '.runtime/tcl_library/tzdata/Asia/Kuwait',
    '.runtime/tcl_library/tzdata/Asia/Macao',
    '.runtime/tcl_library/tzdata/Asia/Macau',
    '.runtime/tcl_library/tzdata/Asia/Magadan',
    '.runtime/tcl_library/tzdata/Asia/Makassar',
    '.runtime/tcl_library/tzdata/Asia/Manila',
    '.runtime/tcl_library/tzdata/Asia/Muscat',
    '.runtime/tcl_library/tzdata/Asia/Nicosia',
    '.runtime/tcl_library/tzdata/Asia/Novokuznetsk',
    '.runtime/tcl_library/tzdata/Asia/Novosibirsk',
    '.runtime/tcl_library/tzdata/Asia/Omsk',
    '.runtime/tcl_library/tzdata/Asia/Oral',
    '.runtime/tcl_library/tzdata/Asia/Phnom_Penh',
    '.runtime/tcl_library/tzdata/Asia/Pontianak',
    '.runtime/tcl_library/tzdata/Asia/Pyongyang',
    '.runtime/tcl_library/tzdata/Asia/Qatar',
    '.runtime/tcl_library/tzdata/Asia/Qostanay',
    '.runtime/tcl_library/tzdata/Asia/Qyzylorda',
    '.runtime/tcl_library/tzdata/Asia/Rangoon',
    '.runtime/tcl_library/tzdata/Asia/Riyadh',
    '.runtime/tcl_library/tzdata/Asia/Saigon',
    '.runtime/tcl_library/tzdata/Asia/Sakhalin',
    '.runtime/tcl_library/tzdata/Asia/Samarkand',
    '.runtime/tcl_library/tzdata/Asia/Seoul',
    '.runtime/tcl_library/tzdata/Asia/Shanghai',
    '.runtime/tcl_library/tzdata/Asia/Singapore',
    '.runtime/tcl_library/tzdata/Asia/Srednekolymsk',
    '.runtime/tcl_library/tzdata/Asia/Taipei',
    '.runtime/tcl_library/tzdata/Asia/Tashkent',
    '.runtime/tcl_library/tzdata/Asia/Tbilisi',
    '.runtime/tcl_library/tzdata/Asia/Tehran',
    '.runtime/tcl_library/tzdata/Asia/Tel_Aviv',
    '.runtime/tcl_library/tzdata/Asia/Thimbu',
    '.runtime/tcl_library/tzdata/Asia/Thimphu',
    '.runtime/tcl_library/tzdata/Asia/Tokyo',
    '.runtime/tcl_library/tzdata/Asia/Tomsk',
    '.runtime/tcl_library/tzdata/Asia/Ujung_Pandang',
    '.runtime/tcl_library/tzdata/Asia/Ulaanbaatar',
    '.runtime/tcl_library/tzdata/Asia/Ulan_Bator',
    '.runtime/tcl_library/tzdata/Asia/Urumqi',
    '.runtime/tcl_library/tzdata/Asia/Ust-Nera',
    '.runtime/tcl_library/tzdata/Asia/Vientiane',
    '.runtime/tcl_library/tzdata/Asia/Vladivostok',
    '.runtime/tcl_library/tzdata/Asia/Yakutsk',
    '.runtime/tcl_library/tzdata/Asia/Yangon',
    '.runtime/tcl_library/tzdata/Asia/Yekaterinburg',
    '.runtime/tcl_library/tzdata/Asia/Yerevan',
    '.runtime/tcl_library/tzdata/Atlantic/Azores',
    '.runtime/tcl_library/tzdata/Atlantic/Bermuda',
    '.runtime/tcl_library/tzdata/Atlantic/Canary',
    '.runtime/tcl_library/tzdata/Atlantic/Cape_Verde',
    '.runtime/tcl_library/tzdata/Atlantic/Faeroe',
    '.runtime/tcl_library/tzdata/Atlantic/Faroe',
    '.runtime/tcl_library/tzdata/Atlantic/Jan_Mayen',
    '.runtime/tcl_library/tzdata/Atlantic/Madeira',
    '.runtime/tcl_library/tzdata/Atlantic/Reykjavik',
    '.runtime/tcl_library/tzdata/Atlantic/South_Georgia',
    '.runtime/tcl_library/tzdata/Atlantic/St_Helena',
    '.runtime/tcl_library/tzdata/Atlantic/Stanley',
    '.runtime/tcl_library/tzdata/Australia/ACT',
    '.runtime/tcl_library/tzdata/Australia/Adelaide',
    '.runtime/tcl_library/tzdata/Australia/Brisbane',
    '.runtime/tcl_library/tzdata/Australia/Broken_Hill',
    '.runtime/tcl_library/tzdata/Australia/Canberra',
    '.runtime/tcl_library/tzdata/Australia/Currie',
    '.runtime/tcl_library/tzdata/Australia/Darwin',
    '.runtime/tcl_library/tzdata/Australia/Eucla',
    '.runtime/tcl_library/tzdata/Australia/Hobart',
    '.runtime/tcl_library/tzdata/Australia/LHI',
    '.runtime/tcl_library/tzdata/Australia/Lindeman',
    '.runtime/tcl_library/tzdata/Australia/Lord_Howe',
    '.runtime/tcl_library/tzdata/Australia/Melbourne',
    '.runtime/tcl_library/tzdata/Australia/NSW',
    '.runtime/tcl_library/tzdata/Australia/North',
    '.runtime/tcl_library/tzdata/Australia/Perth',
    '.runtime/tcl_library/tzdata/Australia/Queensland',
    '.runtime/tcl_library/tzdata/Australia/South',
    '.runtime/tcl_library/tzdata/Australia/Sydney',
    '.runtime/tcl_library/tzdata/Australia/Tasmania',
    '.runtime/tcl_library/tzdata/Australia/Victoria',
    '.runtime/tcl_library/tzdata/Australia/West',
    '.runtime/tcl_library/tzdata/Australia/Yancowinna',
    '.runtime/tcl_library/tzdata/Brazil/Acre',
    '.runtime/tcl_library/tzdata/Brazil/DeNoronha',
    '.runtime/tcl_library/tzdata/Brazil/East',
    '.runtime/tcl_library/tzdata/Brazil/West',
    '.runtime/tcl_library/tzdata/CET',
    '.runtime/tcl_library/tzdata/CST6CDT',
    '.runtime/tcl_library/tzdata/Canada/Atlantic',
    '.runtime/tcl_library/tzdata/Canada/Central',
    '.runtime/tcl_library/tzdata/Canada/Eastern',
    '.runtime/tcl_library/tzdata/Canada/Mountain',
    '.runtime/tcl_library/tzdata/Canada/Newfoundland',
    '.runtime/tcl_library/tzdata/Canada/Pacific',
    '.runtime/tcl_library/tzdata/Canada/Saskatchewan',
    '.runtime/tcl_library/tzdata/Canada/Yukon',
    '.runtime/tcl_library/tzdata/Chile/Continental',
    '.runtime/tcl_library/tzdata/Chile/EasterIsland',
    '.runtime/tcl_library/tzdata/Cuba',
    '.runtime/tcl_library/tzdata/EET',
    '.runtime/tcl_library/tzdata/EST',
    '.runtime/tcl_library/tzdata/EST5EDT',
    '.runtime/tcl_library/tzdata/Egypt',
    '.runtime/tcl_library/tzdata/Eire',
    '.runtime/tcl_library/tzdata/Etc/GMT',
    '.runtime/tcl_library/tzdata/Etc/GMT+0',
    '.runtime/tcl_library/tzdata/Etc/GMT+1',
    '.runtime/tcl_library/tzdata/Etc/GMT+10',
    '.runtime/tcl_library/tzdata/Etc/GMT+11',
    '.runtime/tcl_library/tzdata/Etc/GMT+12',
    '.runtime/tcl_library/tzdata/Etc/GMT+2',
    '.runtime/tcl_library/tzdata/Etc/GMT+3',
    '.runtime/tcl_library/tzdata/Etc/GMT+4',
    '.runtime/tcl_library/tzdata/Etc/GMT+5',
    '.runtime/tcl_library/tzdata/Etc/GMT+6',
    '.runtime/tcl_library/tzdata/Etc/GMT+7',
    '.runtime/tcl_library/tzdata/Etc/GMT+8',
    '.runtime/tcl_library/tzdata/Etc/GMT+9',
    '.runtime/tcl_library/tzdata/Etc/GMT-0',
    '.runtime/tcl_library/tzdata/Etc/GMT-1',
    '.runtime/tcl_library/tzdata/Etc/GMT-10',
    '.runtime/tcl_library/tzdata/Etc/GMT-11',
    '.runtime/tcl_library/tzdata/Etc/GMT-12',
    '.runtime/tcl_library/tzdata/Etc/GMT-13',
    '.runtime/tcl_library/tzdata/Etc/GMT-14',
    '.runtime/tcl_library/tzdata/Etc/GMT-2',
    '.runtime/tcl_library/tzdata/Etc/GMT-3',
    '.runtime/tcl_library/tzdata/Etc/GMT-4',
    '.runtime/tcl_library/tzdata/Etc/GMT-5',
    '.runtime/tcl_library/tzdata/Etc/GMT-6',
    '.runtime/tcl_library/tzdata/Etc/GMT-7',
    '.runtime/tcl_library/tzdata/Etc/GMT-8',
    '.runtime/tcl_library/tzdata/Etc/GMT-9',
    '.runtime/tcl_library/tzdata/Etc/GMT0',
    '.runtime/tcl_library/tzdata/Etc/Greenwich',
    '.runtime/tcl_library/tzdata/Etc/UCT',
    '.runtime/tcl_library/tzdata/Etc/UTC',
    '.runtime/tcl_library/tzdata/Etc/Universal',
    '.runtime/tcl_library/tzdata/Etc/Zulu',
    '.runtime/tcl_library/tzdata/Europe/Amsterdam',
    '.runtime/tcl_library/tzdata/Europe/Andorra',
    '.runtime/tcl_library/tzdata/Europe/Astrakhan',
    '.runtime/tcl_library/tzdata/Europe/Athens',
    '.runtime/tcl_library/tzdata/Europe/Belfast',
    '.runtime/tcl_library/tzdata/Europe/Belgrade',
    '.runtime/tcl_library/tzdata/Europe/Berlin',
    '.runtime/tcl_library/tzdata/Europe/Bratislava',
    '.runtime/tcl_library/tzdata/Europe/Brussels',
    '.runtime/tcl_library/tzdata/Europe/Bucharest',
    '.runtime/tcl_library/tzdata/Europe/Budapest',
    '.runtime/tcl_library/tzdata/Europe/Busingen',
    '.runtime/tcl_library/tzdata/Europe/Chisinau',
    '.runtime/tcl_library/tzdata/Europe/Copenhagen',
    '.runtime/tcl_library/tzdata/Europe/Dublin',
    '.runtime/tcl_library/tzdata/Europe/Gibraltar',
    '.runtime/tcl_library/tzdata/Europe/Guernsey',
    '.runtime/tcl_library/tzdata/Europe/Helsinki',
    '.runtime/tcl_library/tzdata/Europe/Isle_of_Man',
    '.runtime/tcl_library/tzdata/Europe/Istanbul',
    '.runtime/tcl_library/tzdata/Europe/Jersey',
    '.runtime/tcl_library/tzdata/Europe/Kaliningrad',
    '.runtime/tcl_library/tzdata/Europe/Kiev',
    '.runtime/tcl_library/tzdata/Europe/Kirov',
    '.runtime/tcl_library/tzdata/Europe/Kyiv',
    '.runtime/tcl_library/tzdata/Europe/Lisbon',
    '.runtime/tcl_library/tzdata/Europe/Ljubljana',
    '.runtime/tcl_library/tzdata/Europe/London',
    '.runtime/tcl_library/tzdata/Europe/Luxembourg',
    '.runtime/tcl_library/tzdata/Europe/Madrid',
    '.runtime/tcl_library/tzdata/Europe/Malta',
    '.runtime/tcl_library/tzdata/Europe/Mariehamn',
    '.runtime/tcl_library/tzdata/Europe/Minsk',
    '.runtime/tcl_library/tzdata/Europe/Monaco',
    '.runtime/tcl_library/tzdata/Europe/Moscow',
    '.runtime/tcl_library/tzdata/Europe/Nicosia',
    '.runtime/tcl_library/tzdata/Europe/Oslo',
    '.runtime/tcl_library/tzdata/Europe/Paris',
    '.runtime/tcl_library/tzdata/Europe/Podgorica',
    '.runtime/tcl_library/tzdata/Europe/Prague',
    '.runtime/tcl_library/tzdata/Europe/Riga',
    '.runtime/tcl_library/tzdata/Europe/Rome',
    '.runtime/tcl_library/tzdata/Europe/Samara',
    '.runtime/tcl_library/tzdata/Europe/San_Marino',
    '.runtime/tcl_library/tzdata/Europe/Sarajevo',
    '.runtime/tcl_library/tzdata/Europe/Saratov',
    '.runtime/tcl_library/tzdata/Europe/Simferopol',
    '.runtime/tcl_library/tzdata/Europe/Skopje',
    '.runtime/tcl_library/tzdata/Europe/Sofia',
    '.runtime/tcl_library/tzdata/Europe/Stockholm',
    '.runtime/tcl_library/tzdata/Europe/Tallinn',
    '.runtime/tcl_library/tzdata/Europe/Tirane',
    '.runtime/tcl_library/tzdata/Europe/Tiraspol',
    '.runtime/tcl_library/tzdata/Europe/Ulyanovsk',
    '.runtime/tcl_library/tzdata/Europe/Uzhgorod',
    '.runtime/tcl_library/tzdata/Europe/Vaduz',
    '.runtime/tcl_library/tzdata/Europe/Vatican',
    '.runtime/tcl_library/tzdata/Europe/Vienna',
    '.runtime/tcl_library/tzdata/Europe/Vilnius',
    '.runtime/tcl_library/tzdata/Europe/Volgograd',
    '.runtime/tcl_library/tzdata/Europe/Warsaw',
    '.runtime/tcl_library/tzdata/Europe/Zagreb',
    '.runtime/tcl_library/tzdata/Europe/Zaporozhye',
    '.runtime/tcl_library/tzdata/Europe/Zurich',
    '.runtime/tcl_library/tzdata/GB',
    '.runtime/tcl_library/tzdata/GB-Eire',
    '.runtime/tcl_library/tzdata/GMT',
    '.runtime/tcl_library/tzdata/GMT+0',
    '.runtime/tcl_library/tzdata/GMT-0',
    '.runtime/tcl_library/tzdata/GMT0',
    '.runtime/tcl_library/tzdata/Greenwich',
    '.runtime/tcl_library/tzdata/HST',
    '.runtime/tcl_library/tzdata/Hongkong',
    '.runtime/tcl_library/tzdata/Iceland',
    '.runtime/tcl_library/tzdata/Indian/Antananarivo',
    '.runtime/tcl_library/tzdata/Indian/Chagos',
    '.runtime/tcl_library/tzdata/Indian/Christmas',
    '.runtime/tcl_library/tzdata/Indian/Cocos',
    '.runtime/tcl_library/tzdata/Indian/Comoro',
    '.runtime/tcl_library/tzdata/Indian/Kerguelen',
    '.runtime/tcl_library/tzdata/Indian/Mahe',
    '.runtime/tcl_library/tzdata/Indian/Maldives',
    '.runtime/tcl_library/tzdata/Indian/Mauritius',
    '.runtime/tcl_library/tzdata/Indian/Mayotte',
    '.runtime/tcl_library/tzdata/Indian/Reunion',
    '.runtime/tcl_library/tzdata/Iran',
    '.runtime/tcl_library/tzdata/Israel',
    '.runtime/tcl_library/tzdata/Jamaica',
    '.runtime/tcl_library/tzdata/Japan',
    '.runtime/tcl_library/tzdata/Kwajalein',
    '.runtime/tcl_library/tzdata/Libya',
    '.runtime/tcl_library/tzdata/MET',
    '.runtime/tcl_library/tzdata/MST',
    '.runtime/tcl_library/tzdata/MST7MDT',
    '.runtime/tcl_library/tzdata/Mexico/BajaNorte',
    '.runtime/tcl_library/tzdata/Mexico/BajaSur',
    '.runtime/tcl_library/tzdata/Mexico/General',
    '.runtime/tcl_library/tzdata/NZ',
    '.runtime/tcl_library/tzdata/NZ-CHAT',
    '.runtime/tcl_library/tzdata/Navajo',
    '.runtime/tcl_library/tzdata/PRC',
    '.runtime/tcl_library/tzdata/PST8PDT',
    '.runtime/tcl_library/tzdata/Pacific/Apia',
    '.runtime/tcl_library/tzdata/Pacific/Auckland',
    '.runtime/tcl_library/tzdata/Pacific/Bougainville',
    '.runtime/tcl_library/tzdata/Pacific/Chatham',
    '.runtime/tcl_library/tzdata/Pacific/Chuuk',
    '.runtime/tcl_library/tzdata/Pacific/Easter',
    '.runtime/tcl_library/tzdata/Pacific/Efate',
    '.runtime/tcl_library/tzdata/Pacific/Enderbury',
    '.runtime/tcl_library/tzdata/Pacific/Fakaofo',
    '.runtime/tcl_library/tzdata/Pacific/Fiji',
    '.runtime/tcl_library/tzdata/Pacific/Funafuti',
    '.runtime/tcl_library/tzdata/Pacific/Galapagos',
    '.runtime/tcl_library/tzdata/Pacific/Gambier',
    '.runtime/tcl_library/tzdata/Pacific/Guadalcanal',
    '.runtime/tcl_library/tzdata/Pacific/Guam',
    '.runtime/tcl_library/tzdata/Pacific/Honolulu',
    '.runtime/tcl_library/tzdata/Pacific/Johnston',
    '.runtime/tcl_library/tzdata/Pacific/Kanton',
    '.runtime/tcl_library/tzdata/Pacific/Kiritimati',
    '.runtime/tcl_library/tzdata/Pacific/Kosrae',
    '.runtime/tcl_library/tzdata/Pacific/Kwajalein',
    '.runtime/tcl_library/tzdata/Pacific/Majuro',
    '.runtime/tcl_library/tzdata/Pacific/Marquesas',
    '.runtime/tcl_library/tzdata/Pacific/Midway',
    '.runtime/tcl_library/tzdata/Pacific/Nauru',
    '.runtime/tcl_library/tzdata/Pacific/Niue',
    '.runtime/tcl_library/tzdata/Pacific/Norfolk',
    '.runtime/tcl_library/tzdata/Pacific/Noumea',
    '.runtime/tcl_library/tzdata/Pacific/Pago_Pago',
    '.runtime/tcl_library/tzdata/Pacific/Palau',
    '.runtime/tcl_library/tzdata/Pacific/Pitcairn',
    '.runtime/tcl_library/tzdata/Pacific/Pohnpei',
    '.runtime/tcl_library/tzdata/Pacific/Ponape',
    '.runtime/tcl_library/tzdata/Pacific/Port_Moresby',
    '.runtime/tcl_library/tzdata/Pacific/Rarotonga',
    '.runtime/tcl_library/tzdata/Pacific/Saipan',
    '.runtime/tcl_library/tzdata/Pacific/Samoa',
    '.runtime/tcl_library/tzdata/Pacific/Tahiti',
    '.runtime/tcl_library/tzdata/Pacific/Tarawa',
    '.runtime/tcl_library/tzdata/Pacific/Tongatapu',
    '.runtime/tcl_library/tzdata/Pacific/Truk',
    '.runtime/tcl_library/tzdata/Pacific/Wake',
    '.runtime/tcl_library/tzdata/Pacific/Wallis',
    '.runtime/tcl_library/tzdata/Pacific/Yap',
    '.runtime/tcl_library/tzdata/Poland',
    '.runtime/tcl_library/tzdata/Portugal',
    '.runtime/tcl_library/tzdata/ROC',
    '.runtime/tcl_library/tzdata/ROK',
    '.runtime/tcl_library/tzdata/Singapore',
    '.runtime/tcl_library/tzdata/Turkey',
    '.runtime/tcl_library/tzdata/UCT',
    '.runtime/tcl_library/tzdata/US/Alaska',
    '.runtime/tcl_library/tzdata/US/Aleutian',
    '.runtime/tcl_library/tzdata/US/Arizona',
    '.runtime/tcl_library/tzdata/US/Central',
    '.runtime/tcl_library/tzdata/US/East-Indiana',
    '.runtime/tcl_library/tzdata/US/Eastern',
    '.runtime/tcl_library/tzdata/US/Hawaii',
    '.runtime/tcl_library/tzdata/US/Indiana-Starke',
    '.runtime/tcl_library/tzdata/US/Michigan',
    '.runtime/tcl_library/tzdata/US/Mountain',
    '.runtime/tcl_library/tzdata/US/Pacific',
    '.runtime/tcl_library/tzdata/US/Samoa',
    '.runtime/tcl_library/tzdata/UTC',
    '.runtime/tcl_library/tzdata/Universal',
    '.runtime/tcl_library/tzdata/W-SU',
    '.runtime/tcl_library/tzdata/WET',
    '.runtime/tcl_library/tzdata/Zulu',
    '.runtime/tcl_library/word.tcl',
    '.runtime/tcl_library/writefile.tcl',
    '.runtime/tk_library/bgerror.tcl',
    '.runtime/tk_library/button.tcl',
    '.runtime/tk_library/choosedir.tcl',
    '.runtime/tk_library/clrpick.tcl',
    '.runtime/tk_library/comdlg.tcl',
    '.runtime/tk_library/console.tcl',
    '.runtime/tk_library/dialog.tcl',
    '.runtime/tk_library/entry.tcl',
    '.runtime/tk_library/focus.tcl',
    '.runtime/tk_library/fontchooser.tcl',
    '.runtime/tk_library/iconbadges.tcl',
    '.runtime/tk_library/iconlist.tcl',
    '.runtime/tk_library/icons.tcl',
    '.runtime/tk_library/images/README',
    '.runtime/tk_library/images/logo.eps',
    '.runtime/tk_library/images/logo100.gif',
    '.runtime/tk_library/images/logo64.gif',
    '.runtime/tk_library/images/logoLarge.gif',
    '.runtime/tk_library/images/logoMed.gif',
    '.runtime/tk_library/images/pwrdLogo.eps',
    '.runtime/tk_library/images/pwrdLogo100.gif',
    '.runtime/tk_library/images/pwrdLogo150.gif',
    '.runtime/tk_library/images/pwrdLogo175.gif',
    '.runtime/tk_library/images/pwrdLogo200.gif',
    '.runtime/tk_library/images/pwrdLogo75.gif',
    '.runtime/tk_library/images/tai-ku.gif',
    '.runtime/tk_library/license.terms',
    '.runtime/tk_library/listbox.tcl',
    '.runtime/tk_library/megawidget.tcl',
    '.runtime/tk_library/menu.tcl',
    '.runtime/tk_library/mkpsenc.tcl',
    '.runtime/tk_library/msgbox.tcl',
    '.runtime/tk_library/msgs/cs.msg',
    '.runtime/tk_library/msgs/da.msg',
    '.runtime/tk_library/msgs/de.msg',
    '.runtime/tk_library/msgs/el.msg',
    '.runtime/tk_library/msgs/en.msg',
    '.runtime/tk_library/msgs/en_gb.msg',
    '.runtime/tk_library/msgs/eo.msg',
    '.runtime/tk_library/msgs/es.msg',
    '.runtime/tk_library/msgs/fi.msg',
    '.runtime/tk_library/msgs/fr.msg',
    '.runtime/tk_library/msgs/hu.msg',
    '.runtime/tk_library/msgs/it.msg',
    '.runtime/tk_library/msgs/nl.msg',
    '.runtime/tk_library/msgs/pl.msg',
    '.runtime/tk_library/msgs/pt.msg',
    '.runtime/tk_library/msgs/ru.msg',
    '.runtime/tk_library/msgs/sv.msg',
    '.runtime/tk_library/msgs/zh_cn.msg',
    '.runtime/tk_library/optMenu.tcl',
    '.runtime/tk_library/palette.tcl',
    '.runtime/tk_library/panedwindow.tcl',
    '.runtime/tk_library/print.tcl',
    '.runtime/tk_library/safetk.tcl',
    '.runtime/tk_library/scale.tcl',
    '.runtime/tk_library/scaling.tcl',
    '.runtime/tk_library/scrlbar.tcl',
    '.runtime/tk_library/spinbox.tcl',
    '.runtime/tk_library/systray.tcl',
    '.runtime/tk_library/tclIndex',
    '.runtime/tk_library/tearoff.tcl',
    '.runtime/tk_library/text.tcl',
    '.runtime/tk_library/tk.tcl',
    '.runtime/tk_library/tkfbox.tcl',
    '.runtime/tk_library/ttk/altTheme.tcl',
    '.runtime/tk_library/ttk/aquaTheme.tcl',
    '.runtime/tk_library/ttk/button.tcl',
    '.runtime/tk_library/ttk/clamTheme.tcl',
    '.runtime/tk_library/ttk/classicTheme.tcl',
    '.runtime/tk_library/ttk/combobox.tcl',
    '.runtime/tk_library/ttk/cursors.tcl',
    '.runtime/tk_library/ttk/defaults.tcl',
    '.runtime/tk_library/ttk/entry.tcl',
    '.runtime/tk_library/ttk/fonts.tcl',
    '.runtime/tk_library/ttk/menubutton.tcl',
    '.runtime/tk_library/ttk/notebook.tcl',
    '.runtime/tk_library/ttk/panedwindow.tcl',
    '.runtime/tk_library/ttk/progress.tcl',
    '.runtime/tk_library/ttk/scale.tcl',
    '.runtime/tk_library/ttk/scrollbar.tcl',
    '.runtime/tk_library/ttk/sizegrip.tcl',
    '.runtime/tk_library/ttk/spinbox.tcl',
    '.runtime/tk_library/ttk/treeview.tcl',
    '.runtime/tk_library/ttk/ttk.tcl',
    '.runtime/tk_library/ttk/utils.tcl',
    '.runtime/tk_library/ttk/vistaTheme.tcl',
    '.runtime/tk_library/ttk/winTheme.tcl',
    '.runtime/tk_library/ttk/xpTheme.tcl',
    '.runtime/tk_library/xmfbox.tcl',
    'AGENTS.md',
    'AuditSuite.spec',
    'INTEGRATION_CONTRACT.md',
    'README.md',
    'account_cases.py',
    'accruals.py',
    'adapters.py',
    'ai_desktop.py',
    'ai_provider.py',
    'ai_workpapers.py',
    'analytics_support.py',
    'analytics_validation.py',
    'app.py',
    'app_paths.py',
    'assets/ICON_SOURCE.md',
    'assets/js-audit.ico',
    'assets/js-audit.png',
    'assets/portable-config.json',
    'cash_analytics/README.md',
    'cash_analytics/__init__.py',
    'cash_analytics/samples.py',
    'ci/audit-suite-v15.yml',
    'ci/audit-suite-v16.yml',
    'ci/audit-suite-v17.yml',
    'ci/audit-suite-v171.yml',
    'ci/audit-suite-v18.yml',
    'ci/audit-suite-v181.yml',
    'ci/audit-suite.yml',
    'common.py',
    'desktop_display.py',
    'display_schema.py',
    'ecl.py',
    'engines/__init__.py',
    'engines/assets/__init__.py',
    'engines/assets/checks.py',
    'engines/assets/data_io.py',
    'engines/assets/engine.py',
    'engines/finance/__init__.py',
    'engines/finance/engine.py',
    'engines/finance/practice_engine.py',
    'engines/finance/v2_checks.py',
    'engines/finance/workbooks.py',
    'engines/sales/__init__.py',
    'engines/sales/data_io.py',
    'engines/sales/ledger_engine.py',
    'engines/sales/match_engine.py',
    'engines/sales/v2_checks.py',
    'estimate_controls.py',
    'exporter.py',
    'extensions.py',
    'fia/README.md',
    'fia/__init__.py',
    'fia/samples.py',
    'fia/verification/교차검토.md',
    'financial_bridge/PROVENANCE.json',
    'financial_bridge/README.md',
    'financial_bridge/__init__.py',
    'financial_bridge/fixtures/financial.json',
    'financial_bridge/fixtures/financial_cases/01_소계차이.json',
    'financial_bridge/fixtures/financial_cases/02_주석차이.json',
    'financial_bridge/fixtures/financial_cases/03_매핑누락.json',
    'financial_bridge/fixtures/financial_cases/04_주석연결누락.json',
    'financial_bridge/fixtures/financial_cases/05_미지원단위.json',
    'financial_bridge/fixtures/financial_cases/06_기간불일치.json',
    'financial_bridge/fixtures/financial_cases/07_계정중복매핑.json',
    'financial_bridge/fixtures/financial_cases/08_순환합계.json',
    'financial_bridge/fixtures/financial_cases/09_천원단위정상.json',
    'financial_bridge/fixtures/financial_cases/10_허용범위내차이.json',
    'financial_bridge/fixtures/financial_cases/11_조정후미지원.json',
    'financial_bridge/fixtures/financial_cases/12_표시부호오류.json',
    'financial_bridge/fixtures/financial_cases/13_합계는맞지만TB불일치.json',
    'financial_bridge/fixtures/financial_cases/cases.json',
    'financial_bridge/validation.json',
    'financial_bridge/vendor/__init__.py',
    'financial_bridge/vendor/common.py',
    'financial_bridge/vendor/financial.py',
    'gla/README.md',
    'gla/__init__.py',
    'gla/benchmark.py',
    'gla/samples.py',
    'gla/verification/benchmark_10000.json',
    'gla/verification/benchmark_README.md',
    'gla/verification/cross_cash_gl_metadata_result.json',
    'gla/verification/validation.json',
    'gla/교차검토_메모.md',
    'inventory.py',
    'leases.py',
    'ledger.py',
    'local_ai_runtime.py',
    'new_specs.json',
    'payroll.py',
    'procedure_catalog.json',
    'procedures.py',
    'raw_accounts/__init__.py',
    'raw_accounts/samples.py',
    'raw_analytics/00_분석자료요청목록.xlsx',
    'raw_analytics/01_GL_TB_합성원천.xlsx',
    'raw_analytics/02_ERP전표로그_합성.xlsx',
    'raw_analytics/03_은행현금_합성원천.xlsx',
    'raw_analytics/04_GLA_정책.xlsx',
    'raw_analytics/README.md',
    'raw_analytics/manifest.json',
    'raw_analytics/verification.json',
    'raw_analytics/verification/pbc_inspection.ndjson',
    'raw_analytics/verification/pbc_preview.png',
    'raw_analytics/verification/render_pbc.mjs',
    'raw_analytics/검증기록.txt',
    'raw_binding.py',
    'raw_input_seed/README.md',
    'raw_input_seed/preparation.json',
    'raw_input_seed/spec.json',
    'raw_input_seed/배포/01_현재프로그램입력/01_원장_리드_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/02_금융상품_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/03_매출_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/04_감가상각_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/05_확장검사_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/06_리스_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/07_대손충당금_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/08_재고평가_합성자료.xlsx',
    'raw_input_seed/배포/01_현재프로그램입력/09_종업원급여_합성자료.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/01_공통_계획_통제.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/02_자금_금융_차입.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/03_매출_매입_재고.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/04_자산_비용_손상.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/05_인사_급여_DB.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/06_세무_자본_연결.xlsx',
    'raw_input_seed/배포/02_절차별원천자료/07_결산_공시_종결.xlsx',
    'raw_input_seed/정상원천증빙.auditpack',
    'raw_sources/README.md',
    'raw_sources/__init__.py',
    'reference_evidence/00_남은절차_자료요청목록.xlsx',
    'reference_evidence/README.md',
    'reference_evidence/합성_원천증빙묶음.pdf',
    'requirements.txt',
    'review_support.py',
    'runtime.py',
    'samples/감사분석/FIA/FIA_01_정상마감전후속입력.xlsx',
    'samples/감사분석/FIA/FIA_02_마감후과거기간전기.xlsx',
    'samples/감사분석/FIA/FIA_03_자기승인.xlsx',
    'samples/감사분석/FIA/FIA_04_추출후미래입력.xlsx',
    'samples/감사분석/FIA/FIA_05_업무시간밖.xlsx',
    'samples/감사분석/FIA/FIA_06_수동전표집중.xlsx',
    'samples/감사분석/FIA/FIA_07_정상유사마감전입력.xlsx',
    'samples/감사분석/FIA/FIA_08_메타누락.xlsx',
    'samples/감사분석/FIA/FIA_09_메타중복.xlsx',
    'samples/감사분석/FIA/FIA_10_타회사.xlsx',
    'samples/감사분석/FIA/FIA_11_기간불일치.xlsx',
    'samples/감사분석/FIA/FIA_12_현재원장불일치.xlsx',
    'samples/감사분석/FIA/FIA_13_유형미확인.xlsx',
    'samples/감사분석/FIA/FIA_14_선승인금지시각역전.xlsx',
    'samples/감사분석/FIA/FIA_15_정상허용선승인.xlsx',
    'samples/감사분석/FIA/FIA_16_승인필수시각누락.xlsx',
    'samples/감사분석/FIA/FIA_17_명시반복재분류.xlsx',
    'samples/감사분석/FIA/FIA_18_수동승인대기.xlsx',
    'samples/감사분석/FIA/FIA_19_부서시스템미확인.xlsx',
    'samples/감사분석/FIA/FIA_20_시간대누락.xlsx',
    'samples/감사분석/FIA/FIA_21_승인미확인.xlsx',
    'samples/감사분석/FIA/FIA_22_같은전표메타충돌.xlsx',
    'samples/감사분석/FIA/cases.json',
    'samples/감사분석/GLA/GLA_01_정상전체규칙.xlsx',
    'samples/감사분석/GLA/GLA_02_고액정상대조.xlsx',
    'samples/감사분석/GLA/GLA_03_고액경계.xlsx',
    'samples/감사분석/GLA/GLA_04_주말전표.xlsx',
    'samples/감사분석/GLA/GLA_04_주말전표_현재원장.xlsx',
    'samples/감사분석/GLA/GLA_05_월말전표.xlsx',
    'samples/감사분석/GLA/GLA_06_동일구성반복.xlsx',
    'samples/감사분석/GLA/GLA_06_동일구성반복_현재원장.xlsx',
    'samples/감사분석/GLA/GLA_07_동액다른계정정상.xlsx',
    'samples/감사분석/GLA/GLA_08_필수설정누락.xlsx',
    'samples/감사분석/GLA/GLA_09_중복설정.xlsx',
    'samples/감사분석/GLA/GLA_10_회사오류.xlsx',
    'samples/감사분석/GLA/GLA_11_기간오류.xlsx',
    'samples/감사분석/GLA/GLA_12_현재원장불일치.xlsx',
    'samples/감사분석/GLA/cases.json',
    'samples/감사분석/cases.json',
    'samples/감사분석/현금분석/cases.json',
    'samples/감사분석/현금분석/현금_01_정상.xlsx',
    'samples/감사분석/현금분석/현금_02_반복지급후보.xlsx',
    'samples/감사분석/현금분석/현금_03_상대계좌집중후보.xlsx',
    'samples/감사분석/현금분석/현금_04_계좌변경직후후보.xlsx',
    'samples/감사분석/현금분석/현금_05_정상반복유사대조.xlsx',
    'samples/감사분석/현금분석/현금_06_합법분할지급대조.xlsx',
    'samples/감사분석/현금분석/현금_07_여러원장합산지급.xlsx',
    'samples/감사분석/현금분석/현금_08_부분배부잔여.xlsx',
    'samples/감사분석/현금분석/현금_09_은행만잔여1원.xlsx',
    'samples/감사분석/현금분석/현금_10_장부만잔여.xlsx',
    'samples/감사분석/현금분석/현금_11_은행누락통제탐지.xlsx',
    'samples/감사분석/현금분석/현금_12_부호반전.xlsx',
    'samples/감사분석/현금분석/현금_13_중복배부.xlsx',
    'samples/감사분석/현금분석/현금_14_과배부.xlsx',
    'samples/감사분석/현금분석/현금_15_은행회사혼입.xlsx',
    'samples/감사분석/현금분석/현금_16_은행기간밖.xlsx',
    'samples/감사분석/현금분석/현금_17_현금원장행선택누락.xlsx',
    'samples/감사분석/현금분석/현금_18_독립행수통제오류.xlsx',
    'samples/감사분석/현금분석/현금_19_은행기말잔액오류.xlsx',
    'samples/감사분석/현금분석/현금_20_규칙메타미제출.xlsx',
    'samples/감사분석/현금분석/현금_21_현재원장불일치.xlsx',
    'samples/감사분석/현금분석/현금_22_자금이체_현재원장.xlsx',
    'samples/감사분석/현금분석/현금_22_정상자금이체대조.xlsx',
    'samples/감사분석/현금분석/현금_23_은행거래ID중복.xlsx',
    'samples/감사분석/현금분석/현금_24_KRW외통화.xlsx',
    'samples/감사분석/현금분석/현금_25_원문금액공란.xlsx',
    'samples/감사분석/현금분석/현금_26_bool금액.xlsx',
    'samples/감사분석/현금분석/현금_27_양방향지급메타모순.xlsx',
    'samples/감사분석/현금분석/현금_28_양방향메타미제출.xlsx',
    'samples/계정별증빙/cash_finance_CASH-01.json',
    'samples/계정별증빙/cash_finance_CASH-02.json',
    'samples/계정별증빙/cash_finance_CASH-03.json',
    'samples/계정별증빙/cash_finance_CASH-04.json',
    'samples/계정별증빙/cash_finance_CASH-05.json',
    'samples/계정별증빙/debt_tax_DEBT-01.json',
    'samples/계정별증빙/debt_tax_DEBT-02.json',
    'samples/계정별증빙/debt_tax_DEBT-03.json',
    'samples/계정별증빙/equity_disclosure_EQUITY-CASE01.json',
    'samples/계정별증빙/equity_disclosure_EQUITY-CASE02.json',
    'samples/계정별증빙/equity_disclosure_EQUITY-CASE03.json',
    'samples/계정별증빙/financial_reporting_FS-01.json',
    'samples/계정별증빙/financial_reporting_FS-02.json',
    'samples/계정별증빙/financial_reporting_FS-03.json',
    'samples/계정별증빙/fixed_assets_ASSET-EARLY-DEPRECIATION.json',
    'samples/계정별증빙/fixed_assets_ASSET-MISSING-TITLE.json',
    'samples/계정별증빙/fixed_assets_ASSET-NORMAL.json',
    'samples/계정별증빙/inventory_ap_INV-01-NORMAL.json',
    'samples/계정별증빙/inventory_ap_INV-02-MISSING-AP.json',
    'samples/계정별증빙/inventory_ap_INV-03-CUTOFF.json',
    'samples/계정별증빙/inventory_ap_INV-04-COUNT-NRV.json',
    'samples/계정별증빙/inventory_ap_INV-05-NULL-NRV.json',
    'samples/계정별증빙/leases_LEASE-01-NORMAL.json',
    'samples/계정별증빙/leases_LEASE-02-LIABILITY-ERROR.json',
    'samples/계정별증빙/leases_LEASE-03-MISSING-RATE.json',
    'samples/계정별증빙/payroll_PAY-001.json',
    'samples/계정별증빙/payroll_PAY-002.json',
    'samples/계정별증빙/payroll_PAY-003.json',
    'samples/계정별증빙/revenue_ar_REV-C01.json',
    'samples/계정별증빙/revenue_ar_REV-C02.json',
    'samples/계정별증빙/revenue_ar_REV-C03.json',
    'samples/계정별증빙/revenue_ar_REV-C04.json',
    'samples/계정별증빙/revenue_ar_REV-C05.json',
    'samples/공통거래/balanced_journal_missing/검증결과.json',
    'samples/공통거래/balanced_journal_missing/공통거래_balanced_journal_missing.auditpack',
    'samples/공통거래/balanced_journal_missing/원장_공통거래.xlsx',
    'samples/공통거래/balanced_journal_missing/원천/spec.json',
    'samples/공통거래/balanced_journal_missing/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/blank_source_amount/검증결과.json',
    'samples/공통거래/blank_source_amount/공통거래_blank_source_amount.auditpack',
    'samples/공통거래/blank_source_amount/원장_공통거래.xlsx',
    'samples/공통거래/blank_source_amount/원천/spec.json',
    'samples/공통거래/blank_source_amount/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/duplicate_allocation/검증결과.json',
    'samples/공통거래/duplicate_allocation/공통거래_duplicate_allocation.auditpack',
    'samples/공통거래/duplicate_allocation/원장_공통거래.xlsx',
    'samples/공통거래/duplicate_allocation/원천/spec.json',
    'samples/공통거래/duplicate_allocation/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/normal/검증결과.json',
    'samples/공통거래/normal/공통거래_normal.auditpack',
    'samples/공통거래/normal/원장_공통거래.xlsx',
    'samples/공통거래/normal/원천/spec.json',
    'samples/공통거래/normal/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/overallocated/검증결과.json',
    'samples/공통거래/overallocated/공통거래_overallocated.auditpack',
    'samples/공통거래/overallocated/원장_공통거래.xlsx',
    'samples/공통거래/overallocated/원천/spec.json',
    'samples/공통거래/overallocated/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/partial_collection/검증결과.json',
    'samples/공통거래/partial_collection/공통거래_partial_collection.auditpack',
    'samples/공통거래/partial_collection/원장_공통거래.xlsx',
    'samples/공통거래/partial_collection/원천/spec.json',
    'samples/공통거래/partial_collection/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/split_payment/검증결과.json',
    'samples/공통거래/split_payment/공통거래_split_payment.auditpack',
    'samples/공통거래/split_payment/원장_공통거래.xlsx',
    'samples/공통거래/split_payment/원천/spec.json',
    'samples/공통거래/split_payment/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/wrong_company/검증결과.json',
    'samples/공통거래/wrong_company/공통거래_wrong_company.auditpack',
    'samples/공통거래/wrong_company/원장_공통거래.xlsx',
    'samples/공통거래/wrong_company/원천/spec.json',
    'samples/공통거래/wrong_company/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/wrong_period/검증결과.json',
    'samples/공통거래/wrong_period/공통거래_wrong_period.auditpack',
    'samples/공통거래/wrong_period/원장_공통거래.xlsx',
    'samples/공통거래/wrong_period/원천/spec.json',
    'samples/공통거래/wrong_period/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/공통거래/wrong_sign/검증결과.json',
    'samples/공통거래/wrong_sign/공통거래_wrong_sign.auditpack',
    'samples/공통거래/wrong_sign/원장_공통거래.xlsx',
    'samples/공통거래/wrong_sign/원천/spec.json',
    'samples/공통거래/wrong_sign/원천/배포/01_현재프로그램입력/01_공통거래_합성자료.xlsx',
    'samples/기존/감가상각/01_정상_5방법.xlsx',
    'samples/기존/감가상각/02_상각차이.xlsx',
    'samples/기존/감가상각/03_원장금액차이.xlsx',
    'samples/기존/감가상각/04_원장누락.xlsx',
    'samples/기존/감가상각/05_공통누락.xlsx',
    'samples/기존/감가상각/06_자산중복.xlsx',
    'samples/기존/감가상각/07_원장중복.xlsx',
    'samples/기존/감가상각/08_사용가능일누락.xlsx',
    'samples/기존/감가상각/09_생산량누락.xlsx',
    'samples/기존/감가상각/10_생산량초과.xlsx',
    'samples/기존/감가상각/11_미지원방법.xlsx',
    'samples/기존/감가상각/12_정률률누락.xlsx',
    'samples/기존/감가상각/13_변경근거누락.xlsx',
    'samples/기존/감가상각/14_변경중복.xlsx',
    'samples/기존/감가상각/15_처분일오류.xlsx',
    'samples/기존/감가상각/16_1원차이보존.xlsx',
    'samples/기존/감가상각/17_상계차이.xlsx',
    'samples/기존/감가상각/18_빈모집단.xlsx',
    'samples/기존/감가상각/19_잔존원가이상.xlsx',
    'samples/기존/감가상각/20_완전상각계속보유.xlsx',
    'samples/기존/감가상각/21_익월개시.xlsx',
    'samples/기존/감가상각/22_처분월제외.xlsx',
    'samples/기존/감가상각/23_월말아님.xlsx',
    'samples/기존/감가상각/24_통제근거누락.xlsx',
    'samples/기존/감가상각/cases.json',
    'samples/기존/감가상각/입력양식.xlsx',
    'samples/기존/금융상품/v2_01_정상.xlsx',
    'samples/기존/금융상품/v2_02_이자끝누락_금액은일치.xlsx',
    'samples/기존/금융상품/v2_03_기산일누락_금액은일치.xlsx',
    'samples/기존/금융상품/v2_04_이자구간하루누락.xlsx',
    'samples/기존/금융상품/v2_05_이자구간하루중복.xlsx',
    'samples/기존/금융상품/v2_06_이자기준누락.xlsx',
    'samples/기존/금융상품/v2_07_과대한이자허용오차.xlsx',
    'samples/기존/금융상품/v2_08_원금허용오차.xlsx',
    'samples/기존/금융상품/v2_09_이자1원차이.xlsx',
    'samples/기존/금융상품/v2_10_상계되는1원차이.xlsx',
    'samples/기존/금융상품/v2_11_이자기준중복.xlsx',
    'samples/기존/금융상품/v2_12_구간ID중복.xlsx',
    'samples/기존/금융상품/v2_13_기간근거문서누락.xlsx',
    'samples/기존/금융상품/v2_cases.json',
    'samples/기존/매출 자동화/v2_01_정상_분할원장.xlsx',
    'samples/기존/매출 자동화/v2_02_청구는있고원장누락.xlsx',
    'samples/기존/매출 자동화/v2_03_원장만있는매출.xlsx',
    'samples/기존/매출 자동화/v2_04_세증빙공통누락.xlsx',
    'samples/기존/매출 자동화/v2_05_증빙과원장동시누락.xlsx',
    'samples/기존/매출 자동화/v2_06_원장1원금액차이.xlsx',
    'samples/기존/매출 자동화/v2_07_원장차이서로상계.xlsx',
    'samples/기존/매출 자동화/v2_08_차대변같이누락_순액동일.xlsx',
    'samples/기존/매출 자동화/v2_09_전표중복.xlsx',
    'samples/기존/매출 자동화/v2_10_다른회사원장.xlsx',
    'samples/기존/매출 자동화/v2_11_기간밖원장.xlsx',
    'samples/기존/매출 자동화/v2_12_원장에부가세포함.xlsx',
    'samples/기존/매출 자동화/v2_13_원장거래처차이.xlsx',
    'samples/기존/매출 자동화/v2_14_통제자료없음.xlsx',
    'samples/기존/매출 자동화/v2_15_통제합계불일치.xlsx',
    'samples/기존/매출 자동화/v2_16_통제기간불일치.xlsx',
    'samples/기존/매출 자동화/v2_17_마지막원장행1원차이.xlsx',
    'samples/기존/매출 자동화/v2_18_원장수식금액.xlsx',
    'samples/기존/매출 자동화/v2_cases.json',
    'samples/재무제표/financial.json',
    'samples/재무제표/financial_cases/01_소계차이.json',
    'samples/재무제표/financial_cases/02_주석차이.json',
    'samples/재무제표/financial_cases/03_매핑누락.json',
    'samples/재무제표/financial_cases/04_주석연결누락.json',
    'samples/재무제표/financial_cases/05_미지원단위.json',
    'samples/재무제표/financial_cases/06_기간불일치.json',
    'samples/재무제표/financial_cases/07_계정중복매핑.json',
    'samples/재무제표/financial_cases/08_순환합계.json',
    'samples/재무제표/financial_cases/09_천원단위정상.json',
    'samples/재무제표/financial_cases/10_허용범위내차이.json',
    'samples/재무제표/financial_cases/11_조정후미지원.json',
    'samples/재무제표/financial_cases/12_표시부호오류.json',
    'samples/재무제표/financial_cases/13_합계는맞지만TB불일치.json',
    'samples/재무제표/financial_cases/cases.json',
    'samples/통합/급여_01_정상.xlsx',
    'samples/통합/급여_02_귀속월누락.xlsx',
    'samples/통합/급여_03_인사고아.xlsx',
    'samples/통합/급여_04_월중복.xlsx',
    'samples/통합/급여_05_퇴사후귀속.xlsx',
    'samples/통합/급여_06_DB모형.xlsx',
    'samples/통합/급여_07_무급일수초과.xlsx',
    'samples/통합/급여_08_공제초과.xlsx',
    'samples/통합/급여_09_상여근거누락.xlsx',
    'samples/통합/급여_10_원장총액불일치.xlsx',
    'samples/통합/급여_11_계좌불일치.xlsx',
    'samples/통합/급여_12_초과지급.xlsx',
    'samples/통합/급여_13_지급고아.xlsx',
    'samples/통합/급여_14_이체중복.xlsx',
    'samples/통합/급여_15_연차음수잔여.xlsx',
    'samples/통합/급여_16_장기연차.xlsx',
    'samples/통합/급여_17_연차환입.xlsx',
    'samples/통합/급여_18_자산배부.xlsx',
    'samples/통합/급여_19_미지급롤포워드.xlsx',
    'samples/통합/급여_20_연차롤포워드.xlsx',
    'samples/통합/급여_21_선급지급미지원.xlsx',
    'samples/통합/급여_22_급여ID통제.xlsx',
    'samples/통합/급여_23_배부율초과.xlsx',
    'samples/통합/급여_24_입사전이체.xlsx',
    'samples/통합/대손_01_정상.xlsx',
    'samples/통합/대손_02_확률합계.xlsx',
    'samples/통합/대손_03_구간공백.xlsx',
    'samples/통합/대손_04_구간중복.xlsx',
    'samples/통합/대손_05_율초과.xlsx',
    'samples/통합/대손_06_개별근거누락.xlsx',
    'samples/통합/대손_07_개별중복혼입.xlsx',
    'samples/통합/대손_08_채권중복.xlsx',
    'samples/통합/대손_09_채권원장동시누락.xlsx',
    'samples/통합/대손_10_만기오류.xlsx',
    'samples/통합/대손_11_음수채권.xlsx',
    'samples/통합/대손_12_변동누락.xlsx',
    'samples/통합/대손_13_원장롤포워드.xlsx',
    'samples/통합/대손_14_시나리오누락.xlsx',
    'samples/통합/대손_15_할인근거누락.xlsx',
    'samples/통합/대손_16_충당금환입.xlsx',
    'samples/통합/대손_17_음수확률.xlsx',
    'samples/통합/대손_18_원장모집단누락.xlsx',
    'samples/통합/대손_19_제각부호오류.xlsx',
    'samples/통합/리스_01_정상.xlsx',
    'samples/통합/리스_02_무이자.xlsx',
    'samples/통합/리스_03_선급.xlsx',
    'samples/통합/리스_04_원가가감.xlsx',
    'samples/통합/리스_05_짧은내용연수.xlsx',
    'samples/통합/리스_06_장기유동분류.xlsx',
    'samples/통합/리스_07_원장누락.xlsx',
    'samples/통합/리스_08_동시누락.xlsx',
    'samples/통합/리스_09_계약중복.xlsx',
    'samples/통합/리스_10_변경계약.xlsx',
    'samples/통합/리스_11_중도개시.xlsx',
    'samples/통합/리스_12_음수할인율.xlsx',
    'samples/통합/리스_13_모집단금액.xlsx',
    'samples/통합/리스_14_원장차이.xlsx',
    'samples/통합/리스_15_분류합계오류.xlsx',
    'samples/통합/리스_16_독립ID오류.xlsx',
    'samples/통합/비용이연_01_정상.xlsx',
    'samples/통합/비용이연_02_미기록부채.xlsx',
    'samples/통합/비용이연_03_선급전액비용.xlsx',
    'samples/통합/비용이연_04_허용차이도검토.xlsx',
    'samples/통합/비용이연_05_일할연도경계.xlsx',
    'samples/통합/비용이연_06_후기귀속.xlsx',
    'samples/통합/비용이연_07_기준일결제.xlsx',
    'samples/통합/비용이연_08_익일결제.xlsx',
    'samples/통합/비용이연_09_전기선급이월.xlsx',
    'samples/통합/비용이연_10_영거래통제.xlsx',
    'samples/통합/비용이연_11_미연결송장.xlsx',
    'samples/통합/비용이연_12_미연결후속지급.xlsx',
    'samples/통합/비용이연_13_상계되는개별오류.xlsx',
    'samples/통합/비용이연_14_원장롤포워드.xlsx',
    'samples/통합/비용이연_15_계약중복.xlsx',
    'samples/통합/비용이연_16_원장누락.xlsx',
    'samples/통합/비용이연_17_송장고아.xlsx',
    'samples/통합/비용이연_18_지급고아.xlsx',
    'samples/통합/비용이연_19_송장거래처.xlsx',
    'samples/통합/비용이연_20_지급거래처.xlsx',
    'samples/통합/비용이연_21_은행참조중복.xlsx',
    'samples/통합/비용이연_22_송장식별중복.xlsx',
    'samples/통합/비용이연_23_송장총액초과.xlsx',
    'samples/통합/비용이연_24_선급분할미지원.xlsx',
    'samples/통합/비용이연_25_선급후속지급.xlsx',
    'samples/통합/비용이연_26_지급음수.xlsx',
    'samples/통합/비용이연_27_기간역전.xlsx',
    'samples/통합/비용이연_28_부분월월할.xlsx',
    'samples/통합/비용이연_29_검색범위밖송장.xlsx',
    'samples/통합/비용이연_30_기준일송장.xlsx',
    'samples/통합/비용이연_31_검색범위밖지급.xlsx',
    'samples/통합/비용이연_32_계약근거누락.xlsx',
    'samples/통합/비용이연_33_외화미지원.xlsx',
    'samples/통합/비용이연_34_자료유형미지원.xlsx',
    'samples/통합/비용이연_35_대상계정밖.xlsx',
    'samples/통합/비용이연_36_통제ID해시.xlsx',
    'samples/통합/비용이연_37_동시자료누락.xlsx',
    'samples/통합/비용이연_38_통제근거누락.xlsx',
    'samples/통합/비용이연_39_통제추출시점.xlsx',
    'samples/통합/비용이연_40_회사혼입.xlsx',
    'samples/통합/비용이연_41_선지급미지원.xlsx',
    'samples/통합/재고평가_01_정상.xlsx',
    'samples/통합/재고평가_02_NRV원가초과.xlsx',
    'samples/통합/재고평가_03_소수수량.xlsx',
    'samples/통합/재고평가_04_NRV음수.xlsx',
    'samples/통합/재고평가_05_NRV누락.xlsx',
    'samples/통합/재고평가_06_명세중복.xlsx',
    'samples/통합/재고평가_07_수량불일치.xlsx',
    'samples/통합/재고평가_08_단위불일치.xlsx',
    'samples/통합/재고평가_09_변동누락.xlsx',
    'samples/통합/재고평가_10_변동고아.xlsx',
    'samples/통합/재고평가_11_원장롤포워드.xlsx',
    'samples/통합/재고평가_12_음수원가.xlsx',
    'samples/통합/재고평가_13_가격근거누락.xlsx',
    'samples/통합/재고평가_14_진부한가격.xlsx',
    'samples/통합/재고평가_15_독립ID불일치.xlsx',
    'samples/통합/재고평가_16_자료동시누락.xlsx',
    'samples/통합/재고평가_17_소수7자리.xlsx',
    'samples/통합/재고평가_18_원재료미지원.xlsx',
    'samples/통합/통합_01_원장정상.xlsx',
    'samples/통합/통합_02_상계되는원장누락.xlsx',
    'samples/통합/통합_03_전표한쪽누락.xlsx',
    'samples/통합/통합_04_전표중복.xlsx',
    'samples/통합/통합_05_TB변동오류.xlsx',
    'samples/통합/통합_06_미매핑.xlsx',
    'samples/통합/통합_07_통제누락.xlsx',
    'samples/통합/통합_08_통제총액오류.xlsx',
    'samples/통합/통합_09_통제중복.xlsx',
    'samples/통합/통합_10_추출시각오류.xlsx',
    'samples/통합/통합_11_회사혼합.xlsx',
    'samples/통합/통합_12_기간밖.xlsx',
    'samples/통합/통합_13_미승인조정.xlsx',
    'samples/통합/통합_14_불균형조정.xlsx',
    'samples/통합/통합_15_연결설정오류.xlsx',
    'samples/통합/통합_16_동시계정누락.xlsx',
    'samples/통합/통합_17_승인조정.xlsx',
    'samples/통합/통합_v1.3_감가상각.xlsx',
    'samples/통합/통합_v1.3_금융상품.xlsx',
    'samples/통합/통합_v1.3_대손충당금.xlsx',
    'samples/통합/통합_v1.3_리스.xlsx',
    'samples/통합/통합_v1.3_매출.xlsx',
    'samples/통합/통합_v1.3_원장_리드.xlsx',
    'samples/통합/통합_v1.3_재고평가.xlsx',
    'samples/통합/통합_v1.3_종업원급여.xlsx',
    'samples/통합/통합_v1.3_확장검사.xlsx',
    'samples/통합/통합_v1.4_원천증빙.auditpack',
    'samples/통합/통합_v1.4_재무제표.json',
    'samples/통합/통합_v1.5_FIA.xlsx',
    'samples/통합/통합_v1.5_GLA.xlsx',
    'samples/통합/통합_v1.5_현금분석.xlsx',
    'samples/통합/통합업무_v1.1_원장정상.xlsx',
    'samples/통합/통합업무_v1.2_원장정상.xlsx',
    'samples/통합/통합업무_v1.2_확장정상.xlsx',
    'samples/통합/통합업무_감가상각정상.xlsx',
    'samples/통합/통합업무_금융정상.xlsx',
    'samples/통합/통합업무_매출정상.xlsx',
    'samples/통합/확장_01_정상.xlsx',
    'samples/통합/확장_02_양쪽은행누락.xlsx',
    'samples/통합/확장_03_은행모호성.xlsx',
    'samples/통합/확장_04_입고미청구.xlsx',
    'samples/통합/확장_05_재고수량차이.xlsx',
    'samples/통합/확장_06_채권없는입금.xlsx',
    'samples/통합/확장_07_실사일다름.xlsx',
    'samples/통합/확장_08_은행중복ID.xlsx',
    'samples_specs.json',
    'sector_demo.py',
    'sector_resources/README.md',
    'sector_resources/companies/JS/inputs/모회사_JS_원장_리드.xlsx',
    'sector_resources/companies/JS/master.json',
    'sector_resources/companies/JS/plan.json',
    'sector_resources/companies/JS/profile.json',
    'sector_resources/companies/JS_AUTO/inputs/비용이연_01_정상.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_감가상각.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_금융상품.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_대손충당금.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_리스.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_매출.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_원장_리드.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_재고평가.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_종업원급여.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.3_확장검사.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.4_원천증빙.auditpack',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.4_재무제표.json',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.5_FIA.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.5_GLA.xlsx',
    'sector_resources/companies/JS_AUTO/inputs/통합_v1.5_현금분석.xlsx',
    'sector_resources/companies/JS_AUTO/master.json',
    'sector_resources/companies/JS_AUTO/plan.json',
    'sector_resources/companies/JS_AUTO/profile.json',
    'sector_resources/companies/JS_BIO/inputs/비용이연_01_정상.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_감가상각.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_금융상품.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_대손충당금.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_리스.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_매출.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_원장_리드.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_재고평가.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_종업원급여.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.3_확장검사.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.4_원천증빙.auditpack',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.4_재무제표.json',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.5_FIA.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.5_GLA.xlsx',
    'sector_resources/companies/JS_BIO/inputs/통합_v1.5_현금분석.xlsx',
    'sector_resources/companies/JS_BIO/master.json',
    'sector_resources/companies/JS_BIO/plan.json',
    'sector_resources/companies/JS_BIO/profile.json',
    'sector_resources/companies/JS_ELEC/inputs/비용이연_01_정상.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_감가상각.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_금융상품.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_대손충당금.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_리스.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_매출.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_원장_리드.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_재고평가.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_종업원급여.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.3_확장검사.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.4_원천증빙.auditpack',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.4_재무제표.json',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.5_FIA.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.5_GLA.xlsx',
    'sector_resources/companies/JS_ELEC/inputs/통합_v1.5_현금분석.xlsx',
    'sector_resources/companies/JS_ELEC/master.json',
    'sector_resources/companies/JS_ELEC/plan.json',
    'sector_resources/companies/JS_ELEC/profile.json',
    'sector_resources/companies/JS_SEMI/inputs/비용이연_01_정상.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_감가상각.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_금융상품.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_대손충당금.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_리스.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_매출.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_원장_리드.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_재고평가.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_종업원급여.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.3_확장검사.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.4_원천증빙.auditpack',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.4_재무제표.json',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.5_FIA.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.5_GLA.xlsx',
    'sector_resources/companies/JS_SEMI/inputs/통합_v1.5_현금분석.xlsx',
    'sector_resources/companies/JS_SEMI/master.json',
    'sector_resources/companies/JS_SEMI/plan.json',
    'sector_resources/companies/JS_SEMI/profile.json',
    'sector_resources/manifest.json',
    'sector_resources/procedure_catalog.json',
    'sector_resources/reference/JS_업종별_항목표.xlsx',
    'sector_resources/reference/official_sources.md',
    'sector_resources/reference/sector_audit_checks.json',
    'sector_resources/reference/sector_profiles.json',
    'templates/FIA_입력양식.xlsx',
    'templates/GLA_입력양식.xlsx',
    'templates/기존/감가상각_v1_입력양식.xlsx',
    'templates/기존/금융상품_v2_입력템플릿.xlsx',
    'templates/기존/매출 자동화_v2_입력템플릿.xlsx',
    'templates/대손충당금_빈입력양식.xlsx',
    'templates/리스_빈입력양식.xlsx',
    'templates/미기록부채비용이연_입력양식.xlsx',
    'templates/원장리드_입력양식.xlsx',
    'templates/재고평가_빈입력양식.xlsx',
    'templates/종업원급여_빈입력양식.xlsx',
    'templates/현금분석_입력양식.xlsx',
    'templates/확장검사_입력양식.xlsx',
    'test_account_cases.py',
    'test_accruals.py',
    'test_ai_desktop.py',
    'test_ai_provider.py',
    'test_ai_workpapers.py',
    'test_app_paths.py',
    'test_cash_analytics.py',
    'test_core_calculation_links.py',
    'test_desktop_display.py',
    'test_estimates.py',
    'test_fia.py',
    'test_financial_bridge.py',
    'test_gla.py',
    'test_integration_v14.py',
    'test_inventory_payroll.py',
    'test_local_ai_runtime.py',
    'test_raw_accounts.py',
    'test_raw_sources.py',
    'test_runtime_gui.py',
    'test_sector_demo.py',
    'test_suite.py',
    'test_v15_integration.py',
    'test_windows_text.py',
    'testdata/raw_source_baseline/README.md',
    'testdata/raw_source_baseline/spec.json',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/01_원장_리드_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/02_금융상품_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/03_매출_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/04_감가상각_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/05_확장검사_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/06_리스_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/07_대손충당금_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/08_재고평가_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/01_현재프로그램입력/09_종업원급여_합성자료.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/01_공통_계획_통제.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/02_자금_금융_차입.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/03_매출_매입_재고.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/04_자산_비용_손상.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/05_인사_급여_DB.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/06_세무_자본_연결.xlsx',
    'testdata/raw_source_baseline/배포/02_절차별원천자료/07_결산_공시_종결.xlsx',
    'tools/analytics_fixtures.py',
    'tools/build_v15.py',
    'tools/build_v16.py',
    'tools/build_v17.py',
    'tools/build_v171.py',
    'tools/build_v18.py',
    'tools/build_v181.py',
    'tools/github_release_v15.py',
    'tools/github_release_v16.py',
    'tools/github_release_v17.py',
    'tools/github_release_v171.py',
    'tools/github_release_v18.py',
    'tools/github_release_v181.py',
    'tools/package_v15.py',
    'tools/package_v16.py',
    'tools/package_v17.py',
    'tools/package_v171.py',
    'tools/package_v18.py',
    'tools/package_v181.py',
    'tools/prepare_raw_seed.py',
    'tools/prepare_sector_resources.py',
    'tools/prepare_sector_resources_v17.py',
    'tools/prepare_v15_example.py',
    'tools/prepare_v15_raw.py',
    'tools/prepare_v15_samples.py',
    'tools/sample_specs.py',
    'tools/verify_export_v15.mjs',
    'tools/verify_export_v16.mjs',
    'tools/verify_export_v17.mjs',
    'tools/verify_export_v171.mjs',
    'tools/verify_headless_v14.py',
    'tools/verify_headless_v15.py',
    'tools/verify_headless_v16.py',
    'tools/verify_headless_v17.py',
    'tools/verify_sectors_headless.py',
    'v12_specs.json',
    'v13_specs.json',
    'verify.py',
    'verify_ai_actual.py',
    'verify_ime_patch.py',
    'verify_v14.py',
    'verify_v15.py',
    'verify_v16.py',
    'verify_v17.py',
    'verify_v171.py',
    'verify_v18.py',
    'window_capture.py',
    'windows.manifest',
    'windows_text.py',
    'worker_cases.json',
    'worker_library/__init__.py',
    'worker_library/cash_finance/HANDOFF.md',
    'worker_library/cash_finance/__init__.py',
    'worker_library/cash_finance/engine.py',
    'worker_library/cash_finance/fixtures.json',
    'worker_library/cash_finance/manifest.json',
    'worker_library/debt_tax/HANDOFF.md',
    'worker_library/debt_tax/__init__.py',
    'worker_library/debt_tax/engine.py',
    'worker_library/debt_tax/fixtures.json',
    'worker_library/debt_tax/manifest.json',
    'worker_library/equity_disclosure/HANDOFF.md',
    'worker_library/equity_disclosure/__init__.py',
    'worker_library/equity_disclosure/engine.py',
    'worker_library/equity_disclosure/fixtures.json',
    'worker_library/equity_disclosure/manifest.json',
    'worker_library/financial_reporting/HANDOFF.md',
    'worker_library/financial_reporting/__init__.py',
    'worker_library/financial_reporting/engine.py',
    'worker_library/financial_reporting/fixtures.json',
    'worker_library/financial_reporting/manifest.json',
    'worker_library/fixed_assets/HANDOFF.md',
    'worker_library/fixed_assets/__init__.py',
    'worker_library/fixed_assets/engine.py',
    'worker_library/fixed_assets/fixtures.json',
    'worker_library/fixed_assets/manifest.json',
    'worker_library/inventory_ap/HANDOFF.md',
    'worker_library/inventory_ap/__init__.py',
    'worker_library/inventory_ap/engine.py',
    'worker_library/inventory_ap/fixtures.json',
    'worker_library/inventory_ap/manifest.json',
    'worker_library/leases/HANDOFF.md',
    'worker_library/leases/__init__.py',
    'worker_library/leases/engine.py',
    'worker_library/leases/fixtures.json',
    'worker_library/leases/manifest.json',
    'worker_library/payroll/HANDOFF.md',
    'worker_library/payroll/__init__.py',
    'worker_library/payroll/engine.py',
    'worker_library/payroll/fixtures.json',
    'worker_library/payroll/manifest.json',
    'worker_library/revenue_ar/HANDOFF.md',
    'worker_library/revenue_ar/__init__.py',
    'worker_library/revenue_ar/engine.py',
    'worker_library/revenue_ar/fixtures.json',
    'worker_library/revenue_ar/manifest.json',
    'workspace.py',
    '검증/.gitkeep',
    '라이선스/PyInstaller/1-COPYING.txt',
    '라이선스/Python-LICENSE.txt',
    '라이선스/THIRD_PARTY_NOTICES.txt',
    '라이선스/altgraph/1-LICENSE',
    '라이선스/defusedxml/1-LICENSE',
    '라이선스/et_xmlfile/1-LICENCE.python',
    '라이선스/et_xmlfile/2-LICENCE.rst',
    '라이선스/openpyxl/1-LICENCE.rst',
    '라이선스/packaging/1-LICENSE',
    '라이선스/packaging/2-LICENSE.APACHE',
    '라이선스/packaging/3-LICENSE.BSD',
    '라이선스/pefile/1-LICENSE',
    '라이선스/pyinstaller-hooks-contrib/1-LICENSE',
    '라이선스/pywin32-ctypes/1-LICENSE.txt',
    '라이선스/setuptools/1-LICENSE',
    '라이선스/setuptools/10-LICENSE.APACHE',
    '라이선스/setuptools/11-LICENSE.BSD',
    '라이선스/setuptools/12-LICENSE',
    '라이선스/setuptools/13-LICENSE',
    '라이선스/setuptools/14-LICENSE.txt',
    '라이선스/setuptools/15-LICENSE',
    '라이선스/setuptools/16-NOTICE',
    '라이선스/setuptools/17-NOTICE',
    '라이선스/setuptools/2-LICENSE',
    '라이선스/setuptools/3-LICENSE',
    '라이선스/setuptools/4-LICENSE',
    '라이선스/setuptools/5-LICENSE',
    '라이선스/setuptools/6-LICENSE',
    '라이선스/setuptools/7-LICENSE',
    '라이선스/setuptools/8-LICENSE',
    '라이선스/setuptools/9-LICENSE',
    '라이선스/tcl_library-license.terms',
    '라이선스/tk_library-license.terms',
    '문서/AI응답계약.md',
    '문서/CI.md',
    '문서/GLA_FIA_현금_사용안내.md',
    '문서/v1.7.1_사용안내.md',
    '문서/v1.7_사용안내.md',
    '문서/v1.8.1_한글입력_수정안내.md',
    '문서/v1.8_사용안내.md',
    '문서/계정계산기_출처.json',
    '문서/공통거래_더미목록.json',
    '문서/기능별_작동설명_노션원고.md',
    '문서/로컬AI_설치안내.md',
    '문서/사용안내.md',
    '문서/업종별_회사선택_사용안내.md',
    '문서/최근_감사분석_AI_참고.md',
))
NEW_REQUIRED = {
    'audit_workflow.py', 'audit_forms.py', 'audit_archive.py', 'workflow_desktop.py',
    'form_registry.json', 'test_audit_workflow.py', 'test_audit_forms.py',
    'test_audit_archive.py', 'test_workflow_desktop.py', 'test_workflow_ui_review.py', 'verify_v19.py',
    'tools/verify_headless_v19.py', 'tools/build_v19.py', 'tools/package_v19.py',
    'tools/github_release_v19.py', 'tools/test_release_v19.py', 'ci/audit-suite-v19.yml',
    '문서/기준서식_대응범위.md', '문서/v1.9_사용안내.md',
}
HISTORICAL_UPDATES = {'tools/prepare_sector_resources.py', 'tools/verify_headless_v14.py'}
BUILD_REQUIRED = HISTORICAL_UPDATES | {'app.py', 'common.py', 'workspace.py', 'exporter.py',
                  'AuditSuite.spec', 'windows.manifest', 'procedure_catalog.json',
                  'assets/js-audit.ico', 'assets/portable-config.json'} | {
                      p for p in NEW_REQUIRED if p.endswith(('.py', '.json', '.yml'))}
VALIDATION_NAME = 'validation-report.json'
WORKFLOW_PATH = '.github/workflows/audit-suite-v19.yml'
WORKFLOW_NAME = 'JS Audit Suite v1.9.0'
IDENTITY = '300881227+JoonseokWon@users.noreply.github.com'
MARKER = '<!-- audit-suite-v1.9.0 -->'
RELEASE_URL = 'https://github.com/' + REPOSITORY + '/releases/tag/' + TAG
DEFAULT_WORKFLOW = """name: JS Audit Suite v1.9.0
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  verify:
    name: Audit Suite Python ${{ matrix.python-version }}
    runs-on: windows-latest
    timeout-minutes: 25
    strategy:
      fail-fast: false
      matrix:
        python-version: ['3.12', '3.14']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: python -m pip install openpyxl==3.1.5 defusedxml==0.7.1
      - name: Unit tests
        run: python -X utf8 -B -m unittest discover -v
      - name: Release policy mock tests
        run: python -X utf8 -B tools/test_release_v19.py
      - name: Headless integration
        run: python -X utf8 -B tools/verify_headless_v19.py --directory "${{ runner.temp }}/audit-suite-v19-${{ matrix.python-version }}"
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def save_state(state):
    write_json(STATE, state)


def load_state():
    if not STATE.is_file():
        raise RuntimeError('릴리스 상태가 없습니다. --mode stage를 먼저 실행하세요.')
    state = json.loads(STATE.read_text(encoding='utf-8'))
    if state.get('repository') != REPOSITORY or state.get('tag') != TAG or state.get('branch') != BRANCH:
        raise RuntimeError('상태 파일의 저장소·태그·브랜치가 이 도구와 다릅니다.')
    return state


def safe_source_path(name):
    if (not isinstance(name, str) or not name.startswith(SOURCE_PREFIX) or '\\' in name or ':' in name
            or len(name) > 240 or re.search(r'[\x00-\x1f]', name)):
        raise RuntimeError('소스 ZIP 경로가 허용 범위 밖입니다.')
    parts = PurePosixPath(name).parts
    if any(p in ('', '.', '..') or p.casefold() == '.git' or p.endswith((' ', '.')) for p in name.split('/')):
        raise RuntimeError('소스 ZIP의 경로 구성요소가 안전하지 않습니다.')
    reserved = {'con', 'prn', 'aux', 'nul'} | {'com' + str(i) for i in range(1, 10)} | {'lpt' + str(i) for i in range(1, 10)}
    if any(p.split('.', 1)[0].casefold() in reserved or any(ch in p for ch in '<>"|?*') for p in parts):
        raise RuntimeError('Windows에서 안전하지 않은 소스 파일명입니다.')
    return name


PUBLIC_ROOT_FILES = {'.gitattributes', 'v12_specs.json', 'test_raw_accounts.py', 'test_core_calculation_links.py', 'test_account_cases.py', 'INTEGRATION_CONTRACT.md', 'procedures.py', 'verify_v16.py', 'README.md', 'analytics_support.py', 'requirements.txt', 'display_schema.py', 'leases.py', 'test_raw_sources.py', 'window_capture.py', 'test_runtime_gui.py', 'test_fia.py', 'verify_v14.py', 'account_cases.py', 'test_integration_v14.py', 'payroll.py', 'test_cash_analytics.py', 'adapters.py', 'ledger.py', 'AuditSuite.spec', 'procedure_catalog.json', 'analytics_validation.py', 'estimate_controls.py', 'v13_specs.json', 'verify.py', 'samples_specs.json', 'review_support.py', 'inventory.py', 'verify_v15.py', 'app.py', 'desktop_display.py', 'extensions.py', 'test_inventory_payroll.py', 'test_estimates.py', 'worker_cases.json', 'test_desktop_display.py', 'test_suite.py', 'accruals.py', 'test_accruals.py', 'workspace.py', 'new_specs.json', 'test_financial_bridge.py', 'windows.manifest', 'common.py', 'test_gla.py', 'runtime.py', 'verify_v18.py', 'raw_binding.py', 'sector_demo.py', '.gitignore', 'ecl.py', 'test_v15_integration.py', 'test_sector_demo.py', 'verify_v17.py', 'AGENTS.md', 'exporter.py'}

PUBLIC_ROOT_FILES.update({'ai_workpapers.py','ai_provider.py','test_ai_workpapers.py',
                          'test_ai_provider.py','verify_v18.py','verify_v171.py',
                          'ai_desktop.py','local_ai_runtime.py','test_ai_desktop.py',
                          'test_local_ai_runtime.py','verify_ai_actual.py'})
PUBLIC_ROOT_FILES.update({'windows_text.py','test_windows_text.py','verify_ime_patch.py',
                          'app_paths.py','test_app_paths.py'})
PUBLIC_ROOT_FILES.update(p for p in NEW_REQUIRED if '/' not in p)

PUBLIC_SOURCE_DIRS = {'engines','raw_sources','raw_accounts','financial_bridge','worker_library',
                     'gla','fia','cash_analytics','samples','templates','testdata','raw_input_seed',
                     'reference_evidence','raw_analytics','sector_resources','.runtime','문서','ci','라이선스','tools','assets','디자인'}
FORBIDDEN_PARTS = {'.git','.venv','node_modules','__pycache__','.env','config.local.json',
                   'adc.json','credentials.json','release-state.json','메일 자동화',
                   '로컬ai','local-ai','local_ai','.ollama','ollama','models','model',
                   'privateprofile','private-profile','private_profile','github공개릴리스',
                   'build','dist','.cache'}


def allowed_public_path(relative):
    safe_source_path(SOURCE_PREFIX+relative)
    parts = PurePosixPath(relative).parts
    if not parts or any(p.casefold() in FORBIDDEN_PARTS or p.casefold().startswith('.env.') for p in parts):
        raise RuntimeError('공개 허용목록 밖의 개인 설정/실행 파일 경로')
    if relative not in BASELINE_PATHS | NEW_REQUIRED:
        raise RuntimeError('고정된 v1.8.1 공개 1739개+v1.9 승인 신규경로 밖의 파일')
    lower = relative.casefold()
    if parts[0].casefold() in ('배포','검증','로컬ai') and relative!='검증/.gitkeep':
        raise RuntimeError('배포·검증·로컬 AI 디렉터리는 공개 소스에서 제외합니다.')
    if parts[0] == '.runtime' and (len(parts)<3 or parts[1] not in ('tcl_library','tk_library')):
        raise RuntimeError('기존 Tcl/Tk 스크립트 외 런타임/AI 캐시 공개 차단')
    compressed_script_data=(relative=='.runtime/tcl_library/cookiejar/public_suffix_list.dat.gz')
    if not compressed_script_data and lower.endswith(('.sqlite3','.sqlite','.db','.db3','.log','.pyc','.pyo','.pem','.p12','.pfx','.key','.exe','.dll','.bin','.gguf','.safetensors','.onnx','.pt','.pth','.zip','.7z','.tar','.gz')):
        raise RuntimeError('소스 공개에 실제 업무 DB/로그/자격증명/실행파일을 포함할 수 없습니다.')
    if len(parts) == 1:
        if relative in PUBLIC_ROOT_FILES:
            return
    elif parts[0] in ('assets','디자인'):
        if relative=='assets/portable-config.json':return
        if len(parts)!=2 or Path(relative).suffix.lower() not in ('.png','.ico','.md'):
            raise RuntimeError('아이콘 자산은 해당 폴더의 PNG/ICO/출처 Markdown만 공개합니다.')
        return
    elif parts[0] in PUBLIC_SOURCE_DIRS:
        return
    elif relative == '검증/.gitkeep':
        return
    elif parts[0] == 'sector_verification' and Path(relative).suffix in ('.json','.md') and len(parts) <= 4:
        return
    raise RuntimeError('감사 전용 소스 허용목록 밖 경로: ' + relative)


def publication_files(path):
    if not path.is_file() or path.stat().st_size > 100 * 1024**2:
        raise RuntimeError('100MB 이하 소스 ZIP이 필요합니다.')
    entries, seen, total = {}, set(), 0
    with ZipFile(path) as z:
        if not 1 <= len(z.infolist()) <= 12000:
            raise RuntimeError('소스 ZIP 파일 개수 한도 오류')
        for info in z.infolist():
            if info.is_dir():
                raise RuntimeError('공개 소스 ZIP은 명시적 파일 항목만 허용합니다.')
            if info.orig_filename != info.filename:
                raise RuntimeError('공개 소스 ZIP 원문 경로 정규화 불일치')
            name = safe_source_path(info.filename)
            normalized = unicodedata.normalize('NFC', name).casefold()
            mode = (info.external_attr >> 16) & 0o170000
            if normalized in seen or mode not in (0, stat.S_IFREG) or info.flag_bits & 1:
                raise RuntimeError('소스 ZIP 중복·symlink·특수파일·암호화 차단')
            seen.add(normalized)
            total += info.file_size
            if info.file_size > 30 * 1024**2 or total > 300 * 1024**2 or info.file_size > max(info.compress_size, 1) * 1000:
                raise RuntimeError('소스 ZIP 압축·크기 한도 초과')
            relative = name[len(SOURCE_PREFIX):]
            allowed_public_path(relative)
            entries[relative] = z.read(info)
    required = {'requirements.txt', 'tools/verify_headless_v17.py', 'ci/audit-suite-v19.yml', '.gitattributes', 'README.md',
                'app.py','common.py','workspace.py','sector_demo.py','sector_resources/manifest.json','AuditSuite.spec',
                'desktop_display.py','windows.manifest','test_desktop_display.py','verify_v18.py',
                'ai_workpapers.py','ai_provider.py','test_ai_workpapers.py','test_ai_provider.py',
                'ai_desktop.py','local_ai_runtime.py','test_ai_desktop.py','test_local_ai_runtime.py',
                'verify_ai_actual.py',
                'test_runtime_gui.py','문서/v1.8_사용안내.md','문서/AI응답계약.md',
                'windows_text.py','test_windows_text.py','verify_ime_patch.py','app_paths.py','test_app_paths.py',
                'tools/github_release_v19.py'}
    if not required | NEW_REQUIRED <= set(entries):
        raise RuntimeError('소스 ZIP에 requirements.txt/headless 검증 도구가 없습니다.')
    if set(entries) != BASELINE_PATHS | NEW_REQUIRED:
        raise RuntimeError('소스 ZIP은 baseline 1739개와 승인 신규파일의 정확한 집합이어야 합니다.')
    if entries['ci/audit-suite-v19.yml'] != DEFAULT_WORKFLOW.encode('utf-8'):
        raise RuntimeError('소스 CI가 검토한 root workflow와 다릅니다.')
    if entries['.gitattributes'].strip() != b'* -text':
        raise RuntimeError('소스 바이트 보존용 .gitattributes 확인 실패')
    return entries


def file_manifest(files):
    return [{'path': path, 'bytes': len(data), 'sha256': sha(data), 'git_blob_sha': git_sha(data)}
            for path, data in sorted(files.items())]


def local_artifacts(windows_name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', windows_name) or windows_name == SOURCE_NAME:
        raise RuntimeError('Windows 첨부파일 이름은 배포 폴더의 ASCII ZIP 이름이어야 합니다.')
    names = [windows_name, SOURCE_NAME, VALIDATION_NAME, 'SHA256SUMS.txt']
    artifacts = {}
    for name in names:
        path = ROOT / '배포' / name
        if not path.is_file() or not 0 < path.stat().st_size < 2 * 1024**3:
            raise RuntimeError('배포 첨부파일 누락/크기 오류: ' + name)
        artifacts[name] = {'name': name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
    validation = json.loads((ROOT / '배포' / VALIDATION_NAME).read_text(encoding='utf-8'))
    validate_current_evidence(validation,artifacts,ROOT/'배포'/windows_name)
    expected = {}
    for line in (ROOT / '배포/SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in expected:
            raise RuntimeError('SHA256SUMS.txt 형식/중복 오류. sha256 + 공백2개 + 파일명 형식 필수')
        expected[match[2]] = match[1]
    if set(expected) != set(names) - {'SHA256SUMS.txt'} or any(artifacts[n]['sha256'] != value for n, value in expected.items()):
        raise RuntimeError('SHA256SUMS.txt 목록 또는 실제 파일 해시가 다릅니다.')
    files=publication_files(ROOT/'배포'/SOURCE_NAME)
    if len(files)!=validation['source']['files']:
        raise RuntimeError('소스 ZIP의 실제 파일 개수가 검증 보고서와 다릅니다.')
    return artifacts,files


def validate_current_evidence(validation,artifacts,windows_zip):
    """Gate current saves/EXE; label prior IME evidence and zero inference."""
    validate_proof(validation)
    exe=validation['exe'];source=validation.get('source')
    if (not isinstance(source,dict) or source.get('name')!=SOURCE_NAME
            or type(source.get('files')) is not int or source['files']<1739+len(NEW_REQUIRED)
            or source.get('previous_public_paths_preserved')!=1739
            or source.get('sha256')!=artifacts[SOURCE_NAME]['sha256']):
        raise RuntimeError('현재 소스 ZIP 해시·이전 1739개 경로 보존 명세가 필요합니다.')
    if validation.get('supported_scope')!=SUPPORTED_SCOPE:
        raise RuntimeError('v1.9.0 지원범위 표시가 다릅니다.')
    with ZipFile(windows_zip) as archive:
        if archive.testzip() is not None:raise RuntimeError('Windows ZIP CRC 검사 실패')
        names=[];seen=set();total=0
        for info in archive.infolist():
            if not info.filename.startswith(WINDOWS_PREFIX) or info.orig_filename!=info.filename:
                raise RuntimeError('Windows ZIP prefix/원문 경로 오류')
            relative=info.filename[len(WINDOWS_PREFIX):]
            if info.is_dir():
                if relative!='데이터/회사별업무/':raise RuntimeError('Windows ZIP 임의 폴더 차단')
                continue
            safe_source_path(SOURCE_PREFIX+relative)
            mode=(info.external_attr>>16)&0o170000
            if relative.casefold() in seen or mode not in (0,stat.S_IFREG) or info.flag_bits&1:
                raise RuntimeError('Windows ZIP 중복·링크·암호화 항목 차단')
            seen.add(relative.casefold());names.append(relative);total+=info.file_size
            if total>2*1024**3:raise RuntimeError('Windows ZIP 크기 한도 초과')
            allowed=(relative in {'실행파일/'+exe['name'],'실행파일/portable-config.json','README.md',VALIDATION_NAME,'파일목록_SHA256.json'}
                     or relative.startswith(('문서/','라이선스/','데이터/업종별_합성원천자료/')))
            if not allowed or relative.lower().endswith(('.sqlite','.sqlite3','.db','.gguf','.safetensors','.pem','.key','.log','.pdf','.docx','.zip','.xlsm')):
                raise RuntimeError('Windows 공개 허용목록 밖의 파일: '+relative)
        path=WINDOWS_PREFIX+'실행파일/'+exe['name']
        if names.count('실행파일/'+exe['name'])!=1:raise RuntimeError('Windows ZIP에 현재 EXE가 정확히 하나 있어야 합니다.')
        payload=archive.read(path)
        if len(payload)!=exe['bytes'] or sha(payload)!=exe['sha256']:
            raise RuntimeError('Windows ZIP의 EXE가 현재 검증 대상과 다릅니다.')
        config='실행파일/portable-config.json'
        if names.count(config)!=1 or json.loads(archive.read(WINDOWS_PREFIX+config).decode('utf-8-sig'))!={'schema_version':1,'data_directory':'../데이터/회사별업무'}:
            raise RuntimeError('EXE 옆 portable-config.json의 상대 데이터 위치가 다릅니다.')
        if json.loads(archive.read(WINDOWS_PREFIX+VALIDATION_NAME))!=validation:
            raise RuntimeError('Windows ZIP 내장 검증 보고서 불일치')
        manifest=json.loads(archive.read(WINDOWS_PREFIX+'파일목록_SHA256.json'))
        if not isinstance(manifest,list) or len(manifest)!=len(names)-1 or {r.get('file') for r in manifest}!=set(names)-{'파일목록_SHA256.json'}:
            raise RuntimeError('Windows ZIP 파일 manifest의 중복/누락 오류')
        for row in manifest:
            payload=archive.read(WINDOWS_PREFIX+row['file'])
            if row.get('bytes')!=len(payload) or row.get('sha256')!=sha(payload):
                raise RuntimeError('Windows ZIP 내용 파일 해시/크기 불일치')


def validate_proof(value):
    if not isinstance(value,dict) or value.get('schema')!=PROOF_SCHEMA or value.get('version')!='1.9.0' or value.get('status')!='passed':
        raise RuntimeError('현재 v1.9.0 final-validation passed 증거가 필요합니다.')
    unit=value.get('unit',{})
    if not isinstance(unit,dict) or type(unit.get('tests')) is not int or unit['tests']<752 or any(type(unit.get(k)) is not int or unit[k]!=0 for k in ('errors','failures','skipped')):
        raise RuntimeError('로컬 전체 단위검사 통과·오류0·실패0·skip0 증거가 필요합니다.')
    headless=value.get('headless',{})
    if not isinstance(headless,dict):raise RuntimeError('소스/EXE 검사 구조 오류')
    source=headless.get('source',{});frozen=headless.get('frozen',{})
    if not isinstance(source,dict) or not isinstance(frozen,dict) or source.get('ok') is not True or frozen.get('ok') is not True or not isinstance(source.get('checks'),list) or not source['checks'] or source['checks']!=frozen.get('checks'):
        raise RuntimeError('현재 소스/EXE의 같은 기호화 업무단언 검사 통과가 필요합니다.')
    for key in ('source_frozen_observations_identical','portable_layout_verified','icon_embedded_verified','unicode_roundtrip_verified'):
        if value.get(key) is not True:raise RuntimeError('현재 실행파일 검증 누락: '+key)
    if type(value.get('current_actual_model_calls')) is not int or value['current_actual_model_calls']!=0:
        raise RuntimeError('v1.9.0 현재 실제 모델 재추론 검증은 0회로 명시해야 합니다.')
    ime=value.get('ime',{})
    if (not isinstance(ime,dict) or ime.get('current_actual_key_test') is not False or ime.get('baseline_version')!='1.8.1'
            or not re.fullmatch('[0-9a-f]{64}',str(ime.get('baseline_evidence_sha256','')))
            or not isinstance(ime.get('scope'),str) or not ime['scope'].strip()):
        raise RuntimeError('기존 v1.8.1 IME 증거 재사용과 현재 실제 키검사 미수행 범위가 필요합니다.')
    exe=value.get('exe',{})
    if (not isinstance(exe,dict) or exe.get('name')!='통합 회계감사 v1.9.0.exe' or type(exe.get('bytes')) is not int or not 0<exe['bytes']<150*1024**2
            or not re.fullmatch('[0-9a-f]{64}',str(exe.get('sha256','')))):
        raise RuntimeError('현재 EXE 이름·크기·SHA256 증거 오류')
    inputs=value.get('build_inputs')
    if not isinstance(inputs,dict) or not BUILD_REQUIRED<=set(inputs):
        raise RuntimeError('현재 v1.9.0 코드·서식·도구·CI의 고정 빌드 입력 manifest가 필요합니다.')
    for path,hash_value in inputs.items():
        allowed_public_path(path)
        if not re.fullmatch('[0-9a-f]{64}',str(hash_value)):raise RuntimeError('빌드 입력 SHA256 형식 오류')
    if value.get('actual_hardware_ime_test') not in (None,False) or value.get('actual_local_inference') not in (None,False):
        raise RuntimeError('이전 버전 실제 IME/AI 검증을 v1.9.0 신규 실측으로 표시할 수 없습니다.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RuntimeError('인증 헤더를 보존하기 위해 GitHub API 리디렉션을 차단했습니다.')


class GitHub:
    def __init__(self):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
        proc = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                              text=True, capture_output=True, env=env, timeout=30)
        if proc.returncode:
            raise RuntimeError('기존 Git 인증을 불러오지 못했습니다. 인증 내용은 출력하지 않습니다.')
        values = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
        self._token = values.get('password')
        if not self._token:
            raise RuntimeError('기존 Git 인증이 없습니다.')
        self._opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, path, data=None, raw=None, optional=False):
        url = path if path.startswith('https://') else 'https://api.github.com/repos/' + REPOSITORY + path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc not in ('api.github.com', 'uploads.github.com') or parsed.username or parsed.password:
            raise RuntimeError('허용된 GitHub 공식 API 주소가 아닙니다.')
        body = raw if raw is not None else json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={
            'Authorization': 'Bearer ' + self._token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'audit-suite-v19-release',
            'Content-Type': 'application/octet-stream' if raw is not None else 'application/json'})
        try:
            with self._opener.open(request, timeout=180) as response:
                output = response.read()
                return json.loads(output) if output else None
        except urllib.error.HTTPError as exc:
            if optional and exc.code in (404, 409):
                return None
            raise RuntimeError(f'GitHub API {method} HTTP {exc.code}: {parsed.path}') from None
        except urllib.error.URLError:
            raise RuntimeError('GitHub API 네트워크 오류. 응답/인증 내용은 출력하지 않습니다.') from None

    def inspect(self):
        user = self.call('GET','https://api.github.com/user')
        if user.get('login') != OWNER:
            raise RuntimeError('인증된 GitHub 계정이 요청한 소유자와 다릅니다.')
        previous = self.call('GET','https://api.github.com/repos/'+PREVIOUS_REPOSITORY)
        if previous.get('full_name') != PREVIOUS_REPOSITORY or previous.get('private') is not True:
            raise RuntimeError('기존 개인 저장소가 비공개 상태인지 확인하지 못했습니다.')
        repo = self.call('GET','')
        if (repo.get('full_name') != REPOSITORY or repo.get('owner',{}).get('login') != OWNER
                or repo.get('private') is not False or repo.get('visibility') != 'public'
                or not repo.get('permissions',{}).get('push') or repo.get('archived')
                or repo.get('default_branch') != BRANCH):
            raise RuntimeError('기존 감사 전용 공개 저장소의 소유자·공개·쓰기·main 상태 확인 실패')
        branches = self.call('GET','/branches?per_page=100')
        if len(branches) != 1 or branches[0]['name'] != BRANCH:
            raise RuntimeError('공개 저장소에 기대하지 않은 브랜치가 있습니다.')
        head = self.call('GET','/git/ref/heads/'+BRANCH)['object']['sha']
        tags = self.call('GET','/tags?per_page=100')
        expected=set(PREVIOUS_RELEASES)
        if len(tags)!=len({t['name'] for t in tags}) or {t['name'] for t in tags} not in (expected,expected|{TAG}):
            raise RuntimeError('공개 저장소의 이전 두 버전/새 태그 집합이 다릅니다.')
        releases = self.call('GET','/releases?per_page=100')
        by_tag={r['tag_name']:r for r in releases}
        if len(releases)!=len(by_tag) or set(by_tag) not in (expected,expected|{TAG}):
            raise RuntimeError('공개 저장소의 이전 두 버전/새 릴리스 집합이 다릅니다.')
        preserved={}
        for old_tag,old_commit in PREVIOUS_RELEASES.items():
            ref=self.call('GET','/git/ref/tags/'+old_tag)
            if tag_commit(self,ref['object'])!=old_commit:
                raise RuntimeError('기존 공개 태그가 변경되었습니다: '+old_tag)
            old_release=by_tag[old_tag]
            if old_release['draft'] or old_release['target_commitish']!=old_commit:
                raise RuntimeError('기존 공개 릴리스의 대상/게시 상태가 다릅니다: '+old_tag)
            preserved[old_tag]={'commit':old_commit,'release_id':old_release['id'],
                                'release_sha256':previous_release_fingerprint(old_release)}
        tag=self.call('GET','/git/ref/tags/'+TAG,optional=True)
        release=by_tag.get(TAG)
        report={'repository':REPOSITORY,'private':False,'previous_repository_private':True,
                'authenticated_owner':OWNER,'exists':True,'repo_id':repo['id'],'head':head,
                'previous_tag':PREVIOUS_TAG,'previous_tag_commit':BASE_COMMIT,
                'previous_releases':preserved,
                'tag_exists':tag is not None,'tag_object':tag.get('object') if tag else None,
                'release':{'id':release['id'],'draft':release['draft'],'prerelease':release['prerelease'],
                           'target_commitish':release['target_commitish'],'url':release['html_url']} if release else None}
        write_json(WORK/'preflight.json',report)
        return report

    def find_release(self):
        found = self.call('GET', '/releases/tags/' + TAG, optional=True)
        if found is not None:
            return found
        for page in range(1, 11):
            releases = self.call('GET', f'/releases?per_page=100&page={page}')
            matches = [r for r in releases if r['tag_name'] == TAG]
            if len(matches) > 1:
                raise RuntimeError('동일 태그 릴리스가 중복되었습니다.')
            if matches:
                return matches[0]
            if len(releases) < 100:
                return None
        raise RuntimeError('릴리스 목록 한도 초과. 동일 태그 여부를 확정하지 못했습니다.')


def previous_release_fingerprint(release):
    fields=('id','tag_name','target_commitish','name','body','draft','prerelease','published_at','created_at','updated_at')
    record={k:release.get(k) for k in fields}
    record['assets']=sorted([{k:a.get(k) for k in ('id','name','size','digest','state','created_at','updated_at')}
                             for a in release.get('assets',[])],key=lambda a:a['name'])
    return sha(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))


def preserved_previous(report,state):
    if (report.get('repo_id')!=state.get('repo_id') or report.get('previous_tag_commit')!=BASE_COMMIT
            or set(report.get('previous_releases',{}))!=set(PREVIOUS_RELEASES)
            or report.get('previous_releases')!=state.get('previous_releases')):
        raise RuntimeError('기존 저장소 ID/v1.7.0·v1.7.1·v1.8.0·v1.8.1 태그·릴리스가 변경되었습니다. 자동 수정하지 않습니다.')


def git(args, *, cwd=CHECKOUT, input_bytes=None, timeout=180):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    # Hooks are never needed for publication; identity is per command, not global.
    hooks = WORK / 'disabled-hooks'
    hooks.mkdir(parents=True, exist_ok=True)
    command = ['git', '-c', 'safe.directory='+CHECKOUT.resolve().as_posix(), '-c', 'core.autocrlf=false', '-c', 'core.filemode=false', '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(hooks),
               '-c', 'user.name=JoonseokWon', '-c', 'user.email=' + IDENTITY] + list(args)
    proc = subprocess.run(command, cwd=cwd, input=input_bytes, capture_output=True, env=env, timeout=timeout)
    if proc.returncode:
        # Git stderr can contain credential-bearing helper diagnostics; omit it.
        raise RuntimeError('Git 작업 실패: ' + next((arg for arg in args if not arg.startswith('-')), 'command') + '. 인증 내용과 상세 출력은 저장하지 않았습니다.')
    return proc.stdout


def checkout_checks():
    if not CHECKOUT.is_dir() or CHECKOUT.is_symlink() or CHECKOUT.resolve() != (WORK.resolve() / 'checkout'):
        raise RuntimeError('릴리스 checkout 경로가 예상 범위를 벗어났습니다.')
    if git(['remote', 'get-url', 'origin']).decode().strip() != REMOTE:
        raise RuntimeError('checkout origin이 지정 저장소와 다릅니다.')
    if not (CHECKOUT / '.git').is_dir() or (CHECKOUT / '.git').is_symlink():
        raise RuntimeError('릴리스 전용 checkout만 사용할 수 있습니다.')


def commit_files(files,state):
    """Clone the exact existing main and append one commit without deleting old files."""
    if CHECKOUT.exists():
        checkout_checks()
    else:
        git(['clone','--branch',BRANCH,'--single-branch','--',REMOTE,str(CHECKOUT)],cwd=WORK,timeout=600)
        checkout_checks()
    if git(['rev-parse','HEAD']).decode().strip() != state['base'] or git(['status','--porcelain=v1','-z']):
        raise RuntimeError('checkout 기준 커밋/작업 상태가 달라졌습니다. 사용자 변경을 덮어쓰지 않습니다.')
    old={}
    for record in git(['ls-tree','-rz','HEAD']).split(b'\0'):
        if record:
            info,path=record.split(b'\t',1);mode,kind,blob=info.split(b' ')
            if kind != b'blob' or mode not in (b'100644',b'100755'):
                raise RuntimeError('기존 저장소의 예상 밖 submodule/symlink 파일을 자동 변경하지 않습니다.')
            old[path.decode('utf-8')]={'mode':mode.decode(),'sha':blob.decode()}
    if not set(OLD_WORKFLOW_PATHS)<=set(old) or WORKFLOW_PATH in old:
        raise RuntimeError('기존/새 workflow 보존 기준이 다릅니다.')
    if set(old)-set(OLD_WORKFLOW_PATHS)-set(files):
        raise RuntimeError('기존 v1.8.1 소스 파일이 새 ZIP에서 누락되었습니다. 자동 삭제하지 않습니다.')
    immutable=('sector_resources/','samples/','templates/','testdata/','raw_input_seed/',
               'reference_evidence/','raw_analytics/','.runtime/','tools/','ci/')
    if any(path.startswith(immutable) and path not in HISTORICAL_UPDATES and git_sha(files[path])!=entry['sha'] for path,entry in old.items() if path in files):
        raise RuntimeError('이전 공개 계산·더미 원천자료·Tcl 스크립트가 변경되었습니다.')
    if any(p.startswith('.github/') for p in files):
        raise RuntimeError('소스 ZIP은 별도 root workflow를 포함할 수 없습니다.')
    workflow=files['ci/audit-suite-v19.yml']
    if workflow != DEFAULT_WORKFLOW.encode('utf-8'):
        raise RuntimeError('검토한 v1.9.0 workflow와 소스 파일이 다릅니다.')
    changes={**files,WORKFLOW_PATH:workflow}
    for relative,data in changes.items():
        path=CHECKOUT/Path(relative)
        if not path.resolve().is_relative_to(CHECKOUT.resolve()) or path.is_symlink():
            raise RuntimeError('공개 checkout 내부 경로 검증 실패')
        if path.exists() and (not path.is_file() or relative not in old or git_sha(path.read_bytes()) != old[relative]['sha']):
            raise RuntimeError('변경 전 checkout 원문 SHA가 기존 추적 파일과 다릅니다.')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    expected_changed={p for p,data in changes.items() if old.get(p,{}).get('sha') != git_sha(data)}
    if not expected_changed:raise RuntimeError('커밋할 변경이 없습니다.')
    pathspec=WORK/'publication-pathspec.nul'
    pathspec.write_bytes(b''.join((':(literal)'+p).encode('utf-8')+b'\0' for p in sorted(changes)))
    git(['add','-f','--pathspec-from-file='+str(pathspec),'--pathspec-file-nul'])
    staged={p.decode('utf-8') for p in git(['diff','--cached','--name-only','-z']).split(b'\0') if p}
    if staged != expected_changed or not staged <= set(changes):
        raise RuntimeError('실제 공개 stage 파일과 명시 변경 허용목록이 다릅니다.')
    index={}
    for record in git(['ls-files','--stage','-z']).split(b'\0'):
        if record:
            info,path=record.split(b'\t',1);mode,blob,stage=info.split(b' ')
            index[path.decode('utf-8')]=(mode.decode(),blob.decode(),stage.decode())
    if set(index) != set(old)|set(changes):
        raise RuntimeError('전체 index에 기존 파일 삭제 또는 허용목록 밖 파일이 있습니다.')
    for relative,data in changes.items():
        if index.get(relative) not in (('100644',git_sha(data),'0'),('100755',git_sha(data),'0')):
            raise RuntimeError('stage의 소스 원문 바이트/모드가 다릅니다.')
    previous_workflows={}
    for old_path in OLD_WORKFLOW_PATHS:
        payload=(CHECKOUT/old_path).read_bytes()
        if git_sha(payload)!=old[old_path]['sha'] or index[old_path][1]!=old[old_path]['sha']:
            raise RuntimeError('기존 root workflow가 변경되었습니다: '+old_path)
        previous_workflows[old_path]=payload
    state.update(additional_files=file_manifest({**previous_workflows,WORKFLOW_PATH:workflow}),
                 staged_paths=sorted(staged),phase='STAGED_LOCAL')
    save_state(state)
    git(['commit','-m','Add human-directed planning, evidence links and archive controls in JS audit suite v1.9.0'])
    commit=git(['rev-parse','HEAD']).decode().strip()
    parents=git(['rev-list','--parents','-n','1','HEAD']).decode().split()
    if parents != [commit,state['base']] or state['base'] != BASE_COMMIT:
        raise RuntimeError('패치 커밋이 지정 v1.8.1 main을 유일 부모로 잇지 않습니다.')
    state.update(phase='COMMITTED',commit=commit,patch_commits=[commit]);save_state(state)


def pinned_artifacts(state):
    assets, files = local_artifacts(state['windows_asset'])
    if assets != state['local_assets'] or file_manifest(files) != state['source_files']:
        raise RuntimeError('처음 stage한 첨부파일/소스가 변경되었습니다. 기존 릴리스 파일을 바꾸지 않습니다.')
    return assets, files


def ensure_assets(api, release, state):
    actual = {a['name']: a for a in release['assets']}
    if len(actual) != len(release['assets']) or set(actual) != set(state['local_assets']):
        raise RuntimeError('릴리스 첨부파일 집합이 기대 목록과 다릅니다.')
    records = []
    for name, expected in state['local_assets'].items():
        asset = actual[name]
        if asset.get('digest') != 'sha256:' + expected['sha256'] or asset.get('size') != expected['bytes'] or asset.get('state') != 'uploaded':
            raise RuntimeError('업로드 첨부파일 SHA256·크기·완료상태 불일치: ' + name)
        records.append(dict(expected, asset_id=asset['id'], url=asset['browser_download_url']))
    return records


def release_notes():
    path = WORK / 'release-notes.md'
    if path.is_file():
        if path.stat().st_size > 100000:
            raise RuntimeError('릴리스 설명 크기 한도 초과')
        return path.read_text(encoding='utf-8')
    return ('통합 감사 프로그램 v1.9.0 사전 릴리스입니다. 지원 범위: '+SUPPORTED_SCOPE+'. '
            '사람이 감사체계·중요성·위험·적용 여부·수행·판단·승인·검토를 입력하고 프로그램은 현재 근거와 누락·연결을 점검합니다.\n\n'
            'F01 후속사건과 FS01 재무제표 대사를 구분하고 모호한 구형 F01은 사람의 명시적 분류를 요구합니다. '
            '예시 서식의 메타데이터·설계상 참고 연결이며 공식 82권의 전체 셀 자동작성이나 기준 전수 준수 인증이 아닙니다. '
            '보관 잠금·명시적 재개 및 새 ZIP의 원본·DB·헤드·조서 취합과 무결성 검증을 지원합니다.\n\n'
            '현재 실제 AI 모델 호출은 0회입니다. 기존 네이티브 편집기의 실제 IME 증거는 v1.8.1 baseline을 재사용하며 '
            'v1.9.0의 새 실제 키입력 검증은 수행하지 않았습니다. 현재 소스·EXE의 Unicode 저장·재열기·XLSX 왕복과 '
            'Python 3.12·3.14 자동검사는 validation-report.json 및 CI 범위에 따릅니다.\n\n'
            '원본 기준서 PDF·공식 예시 ZIP·실제 업무·DB·모델·키·로컬 로그는 공개하지 않습니다. '
            '이름 입력은 본인인증·전자서명이 아니며 사람 내용 승인과 검토 기록은 전체 감사완료·감사의견과 다릅니다. '
            'v1.7.0·v1.7.1·v1.8.0·v1.8.1 태그·릴리스와 기존 네 workflow를 보존합니다.\n')


def stage(api,windows_name):
    report=api.inspect()
    if STATE.exists():
        state=load_state()
        if state['phase'] in ('PUBLISHED','VERIFIED'):
            raise RuntimeError('이미 게시된 패치 릴리스입니다. verify로 확인하세요.')
        pinned_artifacts(state);preserved_previous(report,state)
    else:
        if report['head'] != BASE_COMMIT or report['tag_exists'] or report['release']:
            raise RuntimeError('지정 v1.8.1 main/새 태그 부재 상태가 아닙니다. 덮어쓰지 않습니다.')
        if CHECKOUT.exists():raise RuntimeError('상태 파일 없이 checkout이 존재합니다.')
        assets,files=local_artifacts(windows_name)
        state={'repository':REPOSITORY,'tag':TAG,'branch':BRANCH,'private':False,'base':BASE_COMMIT,
               'repo_id':report['repo_id'],'previous_releases':report['previous_releases'],'phase':'PREPARED',
               'windows_asset':windows_name,'local_assets':assets,'source_files':file_manifest(files)}
        save_state(state)
    if state['phase'] == 'PREPARED':
        if report['head'] != state['base'] or report['tag_exists'] or report['release']:
            raise RuntimeError('준비 이후 main/새 태그/릴리스가 달라졌습니다.')
        _,files=pinned_artifacts(state);commit_files(files,state)
    if state['phase'] == 'STAGED_LOCAL':
        raise RuntimeError('커밋 직전 중단 상태입니다. index와 상태를 검토해야 합니다.')
    if state['phase'] == 'COMMITTED':
        checkout_checks()
        if git(['rev-parse','HEAD']).decode().strip() != state['commit'] or git(['status','--porcelain=v1','-z']):
            raise RuntimeError('공개 커밋의 checkout이 변경되었습니다.')
        current = api.inspect()
        preserved_previous(current,state)
        if current['tag_exists'] or current['release']:
            raise RuntimeError('공개 push 전 저장소/태그/릴리스가 변경되었습니다.')
        if current['head'] == state['base']:
            git(['push','origin','HEAD:refs/heads/'+BRANCH],timeout=600)
        elif current['head'] != state['commit']:
            raise RuntimeError('원격에 다른 내용이 있습니다. 강제 push하지 않습니다.')
        if api.inspect()['head'] != state['commit']:
            raise RuntimeError('공개 push 후 커밋 확인 실패')
        state['phase'] = 'PUSHED';save_state(state)
    if state['phase'] not in ('PUSHED','DRAFT_CREATED','STAGED'):
        raise RuntimeError('이 상태에서는 공개 draft 업로드를 재개할 수 없습니다.')
    pinned_artifacts(state)
    current = api.inspect()
    preserved_previous(current,state)
    if current['head'] != state['commit']:
        raise RuntimeError('공개 저장소의 대상 커밋/ID가 달라졌습니다.')
    if current['tag_exists'] and tag_commit(api,current['tag_object']) != state['commit']:
        raise RuntimeError('동일 태그가 다른 커밋을 가리킵니다.')
    release = api.find_release()
    if release is None:
        release = api.call('POST','/releases',{'tag_name':TAG,'target_commitish':state['commit'],
                           'name':'통합 감사 프로그램 v1.9.0 · 계획·위험·증거·잠금·취합',
                           'body':release_notes(),'draft':True,'prerelease':True,'make_latest':'false'})
    if not release['draft'] or not release['prerelease'] or release['tag_name'] != TAG or release['target_commitish'] != state['commit']:
        raise RuntimeError('공개 draft의 태그/대상 커밋/사전 릴리스 상태가 다릅니다.')
    if state.get('release_id') not in (None,release['id']):
        raise RuntimeError('공개 draft ID가 기존 상태와 다릅니다.')
    state.update(phase='DRAFT_CREATED',release_id=release['id']);save_state(state)
    existing = {a['name']:a for a in release['assets']}
    if len(existing) != len(release['assets']) or not set(existing) <= set(state['local_assets']):
        raise RuntimeError('공개 draft에 예상 밖/중복 첨부파일이 있습니다.')
    for name in state['local_assets']:
        if name in existing:continue
        target = release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':name})
        api.call('POST',target,raw=(ROOT/'배포'/name).read_bytes())
    release = api.call('GET','/releases/'+str(state['release_id']))
    state.update(phase='STAGED',assets=ensure_assets(api,release,state));save_state(state)
    return {'phase':'STAGED','commit':state['commit'],'source_files':len(state['source_files']),
            'assets':len(state['assets']),'private':False,'draft':True,'base_commit':state['base'],'previous_release_preserved':True}


def patch_commits(state):
    chain=state.get('patch_commits',[state.get('commit')])
    if (state.get('base')!=BASE_COMMIT or chain!=[state.get('commit')]
            or not isinstance(state.get('commit'),str) or not re.fullmatch('[0-9a-f]{40}',state['commit'])):
        raise RuntimeError('v1.9.0은 지정 baseline의 단일 자식 커밋만 허용합니다.')
    return chain


def verify_patch_chain(api,state):
    commit=api.call('GET','/git/commits/'+patch_commits(state)[0])
    if [p.get('sha') for p in commit.get('parents',[])]!=[BASE_COMMIT]:
        raise RuntimeError('v1.9.0 커밋은 v1.8.1 baseline의 유일 부모 fast-forward여야 합니다.')
    return commit


def status(api):
    state = load_state()
    if 'commit' not in state:
        return {'phase': state['phase'], 'commit': None, 'runs': []}
    data = api.call('GET', '/actions/runs?' + urllib.parse.urlencode({'head_sha': state['commit'], 'per_page': 100}))
    selected = [r for r in data['workflow_runs'] if r['name'] == WORKFLOW_NAME and r['head_sha'] == state['commit']
                and r.get('path', '').split('@', 1)[0] == WORKFLOW_PATH and r.get('head_branch') == BRANCH and r.get('event') == 'push']
    records = []
    for run in selected:
        jobs = api.call('GET', '/actions/runs/' + str(run['id']) + '/jobs?per_page=100')
        if jobs.get('total_count', 0) > 100:
            raise RuntimeError('CI 작업 목록이 한도를 넘습니다.')
        records.append({'id': run['id'], 'run_number': run['run_number'], 'status': run['status'], 'conclusion': run['conclusion'],
                        'url': run['html_url'], 'jobs': [{'name': j['name'], 'status': j['status'], 'conclusion': j['conclusion'],
                        'steps': [{'name': s['name'], 'conclusion': s.get('conclusion')} for s in j['steps']]} for j in jobs['jobs']]})
    output = {'phase': state['phase'], 'commit': state['commit'], 'runs': sorted(records, key=lambda r: r['id'], reverse=True)}
    write_json(WORK / 'github-actions.json', output)
    return output


def ci_gate(report):
    if not report['runs']:
        raise RuntimeError('해당 커밋의 v1.9.0 push CI가 없습니다.')
    latest = report['runs'][0]
    if latest['status'] != 'completed' or latest['conclusion'] != 'success' or len(latest['jobs']) != 2:
        raise RuntimeError('최신 CI와 Python 2개 작업 성공 전에는 게시하지 않습니다.')
    versions = set()
    for job in latest['jobs']:
        if job['status'] != 'completed' or job['conclusion'] != 'success':
            raise RuntimeError('Python matrix 작업 성공 확인 실패')
        found = re.findall(r'(?<![\d.])3\.(?:12|14)(?![\d.])', job['name'])
        if len(found) != 1:
            raise RuntimeError('CI 작업 이름에서 Python 버전을 확인하지 못했습니다.')
        versions.add(found[0])
        steps = {s['name']: s['conclusion'] for s in job['steps']}
        if steps.get('Unit tests') != 'success' or steps.get('Release policy mock tests') != 'success' or steps.get('Headless integration') != 'success':
            raise RuntimeError('단위 테스트와 headless 통합 검사 단계가 모두 성공해야 합니다.')
    if versions != {'3.12', '3.14'}:
        raise RuntimeError('Python 3.12/3.14 matrix가 모두 성공해야 합니다.')
    return latest


def ensure_release_tag(api,state):
    """Create only this new tag, never move or replace an existing ref."""
    ref=api.call('GET','/git/ref/tags/'+TAG,optional=True)
    if ref is None:
        ref=api.call('POST','/git/refs',{'ref':'refs/tags/'+TAG,'sha':state['commit']})
    if tag_commit(api,ref['object'])!=state['commit']:
        raise RuntimeError('새 태그가 현재 검증된 커밋과 다릅니다. 태그를 덮어쓰지 않습니다.')
    return ref


def publish(api):
    state = load_state()
    if state['phase'] != 'STAGED':
        raise RuntimeError('검증된 STAGED 상태에서만 게시할 수 있습니다.')
    pinned_artifacts(state)
    ci = ci_gate(status(api))
    verify_patch_chain(api,state)
    current = api.inspect()
    preserved_previous(current,state)
    if current['head'] != state['commit'] or current.get('repo_id') != state['repo_id']:
        raise RuntimeError('게시 전 대상 공개 저장소/커밋이 변경되었습니다.')
    if current['tag_exists'] and tag_commit(api, current['tag_object']) != state['commit']:
        raise RuntimeError('기존 태그가 배포 커밋과 다릅니다. 게시하지 않습니다.')
    ensure_release_tag(api,state)
    release = api.call('GET', '/releases/' + str(state['release_id']))
    if not release['draft'] or release['target_commitish'] != state['commit'] or release['tag_name'] != TAG or not release['prerelease']:
        raise RuntimeError('게시할 draft/대상 커밋/태그가 다릅니다.')
    ensure_assets(api, release, state)
    body = release_notes() + '\n\nGitHub 자동 검사: [Python 3.12·3.14 성공 기록](' + ci['url'] + ')\n'
    response = api.call('PATCH', '/releases/' + str(state['release_id']),
                        {'tag_name':TAG,'target_commitish':state['commit'],
                         'draft': False, 'prerelease': True, 'make_latest': 'false', 'body': body})
    state.update(phase='PUBLISHED', url=response['html_url'], published_at=response.get('published_at'), ci=ci)
    save_state(state)
    return verify(api)


def tag_commit(api, obj):
    for _ in range(4):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            raise RuntimeError('태그가 commit/tag 객체를 가리키지 않습니다.')
        obj = api.call('GET', '/git/tags/' + obj['sha'])['object']
    raise RuntimeError('태그 객체 깊이 한도 초과')


def verify(api):
    state = load_state()
    pinned_artifacts(state)
    report = api.inspect()
    preserved_previous(report,state)
    if report['head'] != state['commit'] or report.get('repo_id') != state['repo_id']:
        raise RuntimeError('최종 공개 저장소/커밋이 배포 상태와 다릅니다.')
    release = api.find_release()
    if (release is None or release['draft'] or not release['prerelease'] or release['id'] != state.get('release_id')
            or not report['tag_exists']):
        raise RuntimeError('게시 상태·태그·사전 릴리스 검증 실패')
    if tag_commit(api, report['tag_object']) != state['commit']:
        raise RuntimeError('태그의 최종 커밋이 배포 커밋과 다릅니다.')
    ci = ci_gate(status(api))
    assets = ensure_assets(api, release, state)
    commit = verify_patch_chain(api,state)
    tree = api.call('GET', '/git/trees/' + commit['tree']['sha'] + '?recursive=1')
    if tree.get('truncated'):
        raise RuntimeError('원격 소스 트리 목록이 잘려 exact 검증하지 못했습니다.')
    blobs = {r['path']: r for r in tree['tree'] if r['type'] == 'blob'}
    expected = {r['path']: r for r in state['source_files']}
    if set(blobs) != set(expected) | {r['path'] for r in state['additional_files']}:
        raise RuntimeError('원격 audit-suite 파일 집합이 소스 ZIP과 다릅니다.')
    for row in state['source_files'] + state['additional_files']:
        remote = blobs.get(row['path'])
        if not remote or remote['sha'] != row['git_blob_sha'] or remote.get('size') != row['bytes'] or remote['mode'] not in ('100644', '100755'):
            raise RuntimeError('소스 ZIP/README/CI의 원격 Git blob 바이트가 다릅니다: ' + row['path'])
    output = {'phase': 'VERIFIED', 'repository': REPOSITORY, 'private': False, 'tag': TAG, 'commit': state['commit'],
              'prerelease': True, 'url': release['html_url'], 'source_files': len(expected),
              'remote_git_blob_sha_exact': True, 'base_commit': state['base'], 'patch_commits':patch_commits(state), 'previous_release_preserved': True, 'preserved_tags':sorted(PREVIOUS_RELEASES), 'preserved_workflows':list(OLD_WORKFLOW_PATHS), 'previous_repository_private': True, 'assets': assets, 'ci_url': ci['url']}
    state.update(phase='VERIFIED', url=release['html_url'], ci=ci)
    save_state(state)
    write_json(WORK / 'release-verified.json', output)
    return output


def main():
    parser = argparse.ArgumentParser(description='기존 공개 저장소의 v1.9.0 fast-forward 릴리스 도구')
    parser.add_argument('--mode', required=True, choices=['inspect', 'stage', 'status', 'publish', 'verify'])
    parser.add_argument('--windows-asset', default=DEFAULT_WINDOWS_NAME, help='배포 폴더의 Windows ZIP 이름(stage 신규 시작에만 적용)')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    api = GitHub()
    if args.mode == 'status':
        api.inspect()
    if args.mode == 'inspect':
        output = api.inspect()
    elif args.mode == 'stage':
        output = stage(api, args.windows_asset)
    elif args.mode == 'status':
        output = status(api)
    elif args.mode == 'publish':
        output = publish(api)
    else:
        output = verify(api)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('작업을 중단했습니다. 저장된 상태를 확인한 뒤 재개하세요.', file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        # Only our controlled errors are safe to print. Unexpected exceptions can
        # embed URLs/credential helper output and therefore use a generic message.
        print(str(exc) if isinstance(exc, RuntimeError) else '릴리스 도구 입력/실행 오류. 인증 내용은 출력하지 않습니다.', file=sys.stderr)
        raise SystemExit(1)
