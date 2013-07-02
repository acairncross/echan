import os
import re
import hashlib
import urllib
import random
import datetime
import quopri

import logging

import webapp2
import jinja2

from google.appengine.api import images
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from webapp2_extras.routes import RedirectRoute

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(
  loader = jinja2.FileSystemLoader(template_dir),
  autoescape = True)

THREADS_PER_PAGE = 8

ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
def base62_encode(num, alphabet = ALPHABET):
  if num == 0:
    return alphabet[0]
  arr = []
  base = len(alphabet)
  while num:
    rem = num % base
    num = num / base
    arr.append(alphabet[rem])
  return ''.join(arr)

def render_str(template, **params):
  t = jinja_env.get_template(template)
  return t.render(params)

def board_key(name='eiken'):
  return db.Key.from_path('Board', name)

class Board(db.Model):
  abbreviation = db.StringProperty()
  name = db.StringProperty()
  title = db.StringProperty()

class Post(db.Model):
  username = db.StringProperty()
  tripcode = db.StringProperty()
  email = db.StringProperty()
  subject = db.StringProperty()
  comment = db.TextProperty()
  created = db.DateTimeProperty()
  modified = db.DateTimeProperty()
  postNum = db.IntegerProperty()
  threadNum = db.IntegerProperty()
  isThread = db.BooleanProperty()
  numReplies = db.IntegerProperty()
  image = blobstore.BlobReferenceProperty()
  filename = db.StringProperty()
  filetype = db.StringProperty()
  width = db.IntegerProperty()
  height = db.IntegerProperty()
  thumb = db.BlobProperty()
  imageNum = db.IntegerProperty()
  stickied = db.BooleanProperty()
  locked = db.BooleanProperty()

  def format_comment(self):
    self.renderText = self.comment.replace('>', '&gt;')

    quotelinks = re.findall('&gt;&gt;\d+', self.renderText)
    for ql in quotelinks:
      quotedPostNum = ql[8:]
      quotedPostNumInt = int(quotedPostNum)

      quotedPost = db.Query(Post).filter('postNum',quotedPostNumInt).get()

      if quotedPost:
        link = '/eiken/res/%d#p%d' % (quotedPost.threadNum, quotedPost.postNum)
      else:
        link = '/eiken/res/%d#p%d' % (self.threadNum, quotedPostNumInt)
      self.renderText = self.renderText.replace(ql, ''.join([
        '<a href="'
        , link
        , '" class="quotelink">'
        , ql
        , '</a>']))

    quotes = re.findall('^&gt;.*$', self.renderText, re.MULTILINE)
    for q in quotes:
      quote = q[4:]
      self.renderText = self.renderText.replace(q, ''.join([
        '<span class="quote">'
        , q
        , '</span>']))

    # self.renderText = quopri.decodestring(self.renderText)
    self.renderText = self.renderText.replace('\n', '<br />')

  def render_threadlistingpost(self):
    self.format_comment()
    return render_str('threadlistingpost.html', p=self)

  def render_threadpost(self):
    self.format_comment()
    return render_str('threadpost.html', p=self)

class BaseHandler(webapp2.RequestHandler):
  def write(self, *a, **kw):
    self.response.out.write(*a, **kw)

  def render(self, template, **kw):
    self.write(render_str(template, **kw))

  def error_404(self):
    numImages = 17
    ranNum = int(random.random()*numImages)
    ranNum = ranNum = 0 if ranNum==5000 else ranNum
    self.error(404)
    self.render('404.html', imgId=ranNum)

class HomeHandler(BaseHandler):
  def get(self, page):
    if not page:
      self.render('home.html')
    elif page == 'faq':
      self.render('faq.html')
    elif page == 'japanese':
      self.render('japanese.html')
    else:
      self.error_404()

class BoardHandler(BaseHandler):
  def parseUsername(self, username):
    tripcode = ''
    trip = re.search('(?<=#).*', username)
    if trip:
      username_match = re.search('.*(?=#)', username)
      if username_match:
        username = username_match.group()
      tripcode = base62_encode(int(
        hashlib.md5(trip.group()).hexdigest(),
        16))[:10]
      tripLen = len(tripcode)
      if tripLen <= 10:
        tripcode = '0'*(10-tripLen) + tripcode
      tripcode = '!' + tripcode
    return (username, tripcode)

class ThreadListingHandler(BoardHandler):
  def get(self, pageNum=0):
    uploadUrl = blobstore.create_upload_url('/eiken/post')
    boardTitle = '/eiken/ - Eiken'

    if pageNum:
      pageNum = int(pageNum)
    else:
      pageNum = 0
    if pageNum > 10:
      self.error_404()
      return
    threadOpeners = db.Query(Post)
    threadOpeners = threadOpeners.filter('isThread',True).order('-modified')
    threadOpeners = list(threadOpeners.run(
      offset=THREADS_PER_PAGE*pageNum,
      limit=THREADS_PER_PAGE))

    threads = []
    for t in threadOpeners:
      thread = db.Query(Post)
      thread = thread.filter('threadNum',t.postNum)
      thread = thread.filter('isThread',False).order('-postNum')
      thread = list(thread.run(limit=5))
      thread.reverse()
      curThread = [t]
      for p in thread:
        curThread.append(p)
      thread = curThread
      threads.append(thread)

    self.render(
      'threadlisting.html',
      threads=threads,
      pageNum=pageNum,
      uploadUrl=uploadUrl,
      boardTitle=boardTitle)


class ThreadHandler(BoardHandler):
  def get(self, threadNum):
    uploadUrl = blobstore.create_upload_url('/eiken/post')
    boardTitle = '/eiken/ - Eiken'

    threadNum = int(threadNum)
    posts = db.Query(Post).filter('threadNum',threadNum)
    posts = posts.order('postNum')
    posts = list(posts)

    if not len(posts):
      self.error_404()
      return

    self.render(
      'thread.html',
      posts=posts,
      threadNum=threadNum,
      uploadUrl=uploadUrl,
      boardTitle=boardTitle
      )

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
  def post(self):
    username = self.request.get('username')
    tripcode = ''
    email = self.request.get('email')
    subject = self.request.get('subject')
    comment = self.request.get('comment')
    threadNum = self.request.get('resto')
    isThread = False if threadNum else True
    numReplies = 0
    blobInfo = None
    filename = ''
    filetype = ''
    width = 0
    height = 0
    thumb = None
    imageNum = 0
    stickied = False
    locked = False

    try:
      blobInfo = self.get_uploads('upfile')[0]
    except IndexError:
      if isThread:
        self.render(
          'error.html',
          boardTitle='/eiken/ - Eiken',
          errorMessage='No file selected',
          returnPath='/eiken/',
          )
        return

    if not comment and not isThread and not blobInfo:
      self.render(
        'error.html',
        boardTitle='/eiken/ - Eiken',
        errorMessage='No text entered.',
        returnPath='/eiken/res/%s' % threadNum,
        )
      return

    if blobInfo:
      filename = self.request.POST['upfile'].filename

      validTypes = [
        'image/bmp',
        'image/jpeg',
        'image/png',
        'image/gif'
        ]

      if blobInfo.content_type not in validTypes:
        self.render(
          'error.html',
          boardTitle='/eiken/ - Eiken',
          errorMessage='Cannot recognise filetype.',
          returnPath='/eiken/')
        return

      if blobInfo.content_type == 'image/bmp':
        filetype = 'bmp'
      elif blobInfo.content_type == 'image/jpeg':
        filetype = 'jpg'
      elif blobInfo.content_type == 'image/png':
        filetype = 'png'
      elif blobInfo.content_type == 'image/gif':
        filetype = 'gif'

      img = images.Image(image_data=blobInfo.open().read())
      width = img.width
      height = img.height
      if isThread:
        img.resize(width=250, height=250)
      else:
        img.resize(width=125, height=125)
      thumb = img.execute_transforms()
      thumb = db.Blob(thumb)

      mostRecentImgPost = db.Query(Post).filter('imageNum >',0)
      mostRecentImgPost = mostRecentImgPost.order('-imageNum').get()

      if mostRecentImgPost:
        imageCount = mostRecentImgPost.imageNum
      else:
        imageCount = 0

      imageNum = imageCount + 1

    trip = re.search('(?<=#).*', username)
    if trip:
      usernameMatch = re.search('.*(?=#)', username)
      if usernameMatch:
        username = usernameMatch.group()
      tripcode = base62_encode(int(
        hashlib.md5(trip.group()).hexdigest(),
        16))[:10]
      tripLen = len(tripcode)
      if tripLen <= 10:
        tripcode = '0'*(10-tripLen) + tripcode
      tripcode = '!' + tripcode

    if not username:
      username = 'Anonymous'

    comment = comment.strip()

    mostRecentPost = db.Query(Post).order('-postNum').get()
    if mostRecentPost:
      postCount = mostRecentPost.postNum
    else:
      postCount = 0

    postNum = postCount + 1

    created = modified = datetime.datetime.now()

    if isThread:
      threadNum = postNum
      parent = board_key()
    else:
      threadNum = int(threadNum)
      parent = db.Query(Post).filter('threadNum',threadNum)
      parent = parent.filter('isThread',True).get()
      parent.numReplies += 1
      if email != 'sage':
        parent.modified = created
      parent.put()

    p = Post(
      parent=parent,
      username=username,
      tripcode=tripcode,
      email=email,
      subject=subject,
      comment=comment,
      created=created,
      modified=modified,
      postNum=postNum,
      threadNum=threadNum,
      isThread=isThread,
      numReplies=numReplies,
      image=blobInfo,
      filename=filename,
      filetype=filetype,
      width=width,
      height=height,
      thumb=thumb,
      imageNum=imageNum,
      stickied=stickied,
      locked=locked
      )
    p.put()
    self.redirect('/eiken/')

  def write(self, *a, **kw):
    self.response.out.write(*a, **kw)

  def render(self, template, **kw):
    self.write(render_str(template, **kw))

class ImageHandler(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, imageNum, extension):
    validExtensions = ['jpg','png','bmp','gif']
    if extension not in validExtensions:
      self.error_404()
      return
    imageNum = int(imageNum)
    post = db.Query(Post).filter('imageNum',imageNum).get()
    blobInfo = post.image
    if extension == post.filetype:
      self.send_blob(blobInfo)
    else:
      self.error_404()

  def write(self, *a, **kw):
    self.response.out.write(*a, **kw)

  def render(self, template, **kw):
    self.write(render_str(template, **kw))

  def error_404(self):
    numImages = 17
    ranNum = int(random.random()*numImages)
    self.error(404)
    self.render('404.html', imgId=ranNum)

class ThumbHandler(BaseHandler):
  def get(self, imageNum):
    imageNum = int(imageNum)
    post = db.Query(Post).filter('imageNum',imageNum).get()
    if post.thumb:
      self.response.headers['Content-Type'] = 'image/png'
      self.response.out.write(post.thumb)
    else:
      self.response.out.write('No image')

class BonusPage(BaseHandler):
  def get(self):
    passTripTuples = []
    numTripcodes = 50
    ranWords = []
    numRanWords = 3
    for i in range(numTripcodes):
      curWords = []
      for j in range(numRanWords):
        ranNum = int(random.random()*5000)
        ranNum = 0 if ranNum==5000 else ranNum
        curWords.append(lines[ranNum].strip())
      ranWords.append(curWords)
    for ranWordGroup in ranWords:
      password = ''.join(ranWordGroup)
      tripcode = base62_encode(int(hashlib.md5(password).hexdigest(), 16))[:10]
      tripLen = len(tripcode)
      if tripLen <= 10:
        tripcode = '0'*(10-tripLen) + tripcode
      tripcode = '!' + tripcode
      passTripTuples.append((password, tripcode))
    self.render('bonus.html', passTripTuples=passTripTuples)

app = webapp2.WSGIApplication([
    RedirectRoute(
      '/eiken/', ThreadListingHandler,
      name='main',
      strict_slash=True),
    ('/eiken/(\d*)', ThreadListingHandler),
    ('/eiken/res/(\d+)', ThreadHandler),
    ('/eiken/post', UploadHandler),
    ('/eiken/src/(\d+)\.([a-zA-Z]{3})', ImageHandler),
    ('/eiken/thumb/(\d+).png', ThumbHandler),
    ('/(\w*)', HomeHandler)
  ], debug=True)