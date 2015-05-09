#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Copyright (C) 2012-2015 emijrp <emijrp@gmail.com>
# Copyright (C) 2015 Matt Hazinski <matt@hazinski.net>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Instructions:
 1) Create a subdirectory "download" and add a videostodo.txt file with YouTube links.
 2) In the current directory, create a keys.txt file with your IA S3 keys. Accesskey and secretkey in two separated lines.
 3) Install youtube-dl
 4) Modify preferences if desired (see below).
 5) Run this script: python youtube2internetarchive.py [english|spanish] [cc|all] [collectionname]
    (where param 1 is language for the video dates,
     param 2 is a filter to upload only Creative Commons or all
     param 3 is the collection name in Internet Archive)
"""

# Keys: http://archive.org/account/s3.php
# Documentation: http://archive.org/help/abouts3.txt
# https://wiki.archive.org/twiki/bin/view/Main/IAS3BulkUploader

import json
import os
import glob
import re
import subprocess
import sys
import time
import unicodedata
import urllib
import internetarchive

def removeoddchars(s):
    #http://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-in-a-python-unicode-string
    s = ''.join((c for c in unicodedata.normalize('NFD', u'%s' % s) if unicodedata.category(c) != 'Mn'))
    s = re.sub(ur"(?im)[^a-z0-9_\.-]", ur"", s) # greek chars and others cause errors in item name if not removed
    return s

def updatetodo(l):
    f = open('videostodo.txt', 'w')
    f.write('\n'.join(l))
    f.close()

def main():
    num2month = { 
        'spanish': {'01':'enero', '02': 'febrero', '03':'marzo', '04':'abril', '05':'mayo', '06':'junio', '07':'julio', '08':'agosto','09':'septiembre','10':'octubre', '11':'noviembre', '12':'diciembre'},
        'english': {'01':'january', '02': 'february', '03':'march', '04':'april', '05':'may', '06':'june', '07':'july', '08':'august','09':'september','10':'october', '11':'november', '12':'december'},
    }
    
    # Start preferences
    
    overwrite = True
    if len(sys.argv) < 4:
        print 'python youtube2internetarchive.py [english|spanish] [cc|all] [collectionname]'
        sys.exit()

    language = sys.argv[1]
    if language not in num2month.keys():
        print 'Bad language parameter'
        print 'Allowed:', num2month.keys()
        sys.exit()

    cc = sys.argv[2].lower() == 'cc' and True or False
    collection = sys.argv[3]
    # End preferences

    accesskey = open('keys.txt', 'r').readlines()[0].strip()
    secretkey = open('keys.txt', 'r').readlines()[1].strip()
    videotodourls = [l.strip() for l in open('videostodo.txt', 'r').readlines()]
    print videotodourls
    
    while len(videotodourls) > 0:
        videotodourl = videotodourls[0]
        videohtml = unicode(urllib.urlopen(videotodourl).read(), 'utf-8')
        videoid = videotodourl.split('watch?v=')[1]
        if len(videoid) < 11:
            print 'Error en video id'
            continue
        
        #check if it is on IA
        f = urllib.urlopen('https://archive.org/search.php?query=%s%%20subject%%3A"spanishrevolution"' % (videoid))
        raw = f.read()
        if not re.search(ur'Your search did not match any items in the Archive', raw):
            print u'Ya esta en Internet Archive'
            videotodourls.remove(videotodourl)
            updatetodo(videotodourls)
            continue
        
        #verify license in youtube
        if cc and not re.search(ur"(?i)/t/creative_commons", videohtml):
            print "It is not Creative Commons", videotodourl
            videotodourls.remove(videotodourl)
            updatetodo(videotodourls)
            continue
        
        #get tags
        tags = re.findall(ur'<meta property="og:video:tag" content="([^<>]+)">', videohtml)
        
        #download video and info
        os.system('./youtube-dl --write-info-json --write-description --all-subs %s' % (videotodourl))
        
        jsonfilename = glob.glob('*%s.info.json' % (videoid))
        if not jsonfilename:
            print 'No se encontro el json del video'
            sys.exit()
        elif len(jsonfilename) > 1:
            print 'Se ha encontrado mas de un json coincidente'
            sys.exit()
        
        jsonfilename = jsonfilename[0]
        json_ = json.loads(unicode(open(jsonfilename, 'r').read(), 'utf-8'))
        upload_date = json_['upload_date'][:4] + '-' + json_['upload_date'][4:6] + '-' + json_['upload_date'][6:8]
        upload_year = json_['upload_date'][:4]
        upload_month = num2month[language][json_['upload_date'][4:6]]
        description = json_['description']
        uploader = json_['uploader']
        title = re.sub(u"%", u"/", json_['title']) # 6%7
        
        videofilename = glob.glob('*-%s.mp4' % (videoid))
        if not videofilename:
            print 'No se encontro el video'
            sys.exit()
        elif len(videofilename) > 1:
            print 'Se ha encontrado mas de un video coincidente'
            sys.exit()
        
        videofilename = videofilename[0]
        itemname = removeoddchars('%s-%s' % (collection, videofilename.split(videoid)[0][:-1])) # [:-1] to remove the -
        itemname = itemname[:88] + '-' + videoid
        videofilename_ = removeoddchars(videofilename)
        if not re.search(ur"Item cannot be found", unicode(urllib.urlopen('http://archive.org/details/%s' % (itemname)).read(), 'utf-8')):
            print 'That item exists at Internet Archive', 'http://archive.org/details/%s' % (itemname)
            if not overwrite:
                print 'Marking as done and skiping...'
                videotodourls.remove(videotodourl)
                updatetodo(videotodourls)
                continue
            else:
                print 'Reuploading...'
      
        subject = (u'; '.join([collection, upload_month, upload_year] + tags)) 

        item = internetarchive.get_item(itemname)
        md = dict(mediatype='movies', creator=uploader, language=language, collection=collection, title=title, description=u'{0} <br/><br/>Source: <a href="{1}">{2}</a><br/>Uploader: <a href="http://www.youtube.com/user/{3}">{4}</a><br/>Upload date: {5}'.format(description, videotodourl, videotodourl, uploader, uploader, upload_date), date=upload_date, year=upload_year, subject=subject, originalurl=videotodourl, licenseurl=(cc and 'http://creativecommons.org/licenses/by/3.0/' or ''))
        
        print 'Se van a subir los ficheros'
        print glob.glob('*%s*' % (videoid))
        
        item.upload(glob.glob('*-%s.*' % (videoid)), metadata=md, access_key=accesskey, secret_key=secretkey)

        print 'You can browse it in https://archive.org/details/%s' % (itemname)
        #videotodourls.remove(videotodourl)
        #updatetodo(videotodourls)

if __name__ == '__main__':
    main()
