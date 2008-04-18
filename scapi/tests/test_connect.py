from __future__ import with_statement
import os
import tempfile
from ConfigParser import SafeConfigParser
import pkg_resources
import scapi
import scapi.authentication
import logging
import webbrowser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
_logger = logging.getLogger("scapi")
#_logger.setLevel(logging.DEBUG)

RUN_INTERACTIVE_TESTS = False
USE_OAUTH = True

TOKEN  = ""
SECRET = ""
CONSUMER = ""
CONSUMER_SECRET = ""
API_HOST = ""
USER = ""
PASSWORD = ""

CONFIG_NAME = "soundcloud.cfg"

def load_config(config_name=None):
    global TOKEN, SECRET, CONSUMER_SECRET, CONSUMER, API_HOST, USER, PASSWORD
    if config_name is None:
        config_name = CONFIG_NAME
    parser = SafeConfigParser()
    current = os.getcwd()
    while current:
        name = os.path.join(current, config_name)
        if os.path.exists(name):
            parser.read([name])
            TOKEN = parser.get('global', 'accesstoken')
            SECRET = parser.get('global', 'accesstoken_secret')
            CONSUMER = parser.get('global', 'consumer')
            CONSUMER_SECRET = parser.get('global', 'consumer_secret')
            API_HOST = parser.get('global', 'host')
            USER = parser.get('global', 'user')
            PASSWORD = parser.get('global', 'password')
            logger.debug("token: %s", TOKEN)
            logger.debug("secret: %s", SECRET)
            logger.debug("consumer: %s", CONSUMER)
            logger.debug("consumer_secret: %s", CONSUMER_SECRET)
            logger.debug("user: %s", USER)
            logger.debug("password: %s", PASSWORD)
            logger.debug("host: %s", API_HOST)
            break
        new_current = os.path.dirname(current)
        if new_current == current:
            break
        current = new_current
    

def test_load_config():
    base = tempfile.mkdtemp()
    oldcwd = os.getcwd()
    cdir = os.path.join(base, "foo")
    os.mkdir(cdir)
    os.chdir(cdir)
    test_config = """
[global]
host=host
consumer=consumer
consumer_secret=consumer_secret
accesstoken=accesstoken
accesstoken_secret=accesstoken_secret
user=user
password=password
"""
    with open(os.path.join(base, CONFIG_NAME), "w") as cf:
        cf.write(test_config)
    load_config()
    assert TOKEN == "accesstoken" and SECRET == "accesstoken_secret" and API_HOST == 'host'
    assert CONSUMER == "consumer" and CONSUMER_SECRET == "consumer_secret"
    assert USER == "user" and PASSWORD == "password"
    os.chdir(oldcwd)
    load_config()
    
def setup():
    load_config()
    #scapi.SoundCloudAPI(host='192.168.2.101:3000', user='tiga', password='test')
    #scapi.SoundCloudAPI(host='staging-api.soundcloud.com:3030', user='tiga', password='test')
    scapi.USE_PROXY = True
    scapi.PROXY = 'http://127.0.0.1:10000/'

    if USE_OAUTH:
        authenticator = scapi.authentication.OAuthAuthenticator(CONSUMER, 
                                                                CONSUMER_SECRET,
                                                                TOKEN, 
                                                                SECRET)
    else:
        authenticator = scapi.authentication.BasicAuthenticator(USER, PASSWORD, CONSUMER, CONSUMER_SECRET)
    scapi.SoundCloudAPI(host=API_HOST, 
                        authenticator=authenticator)
    
def test_connect():
    #sca = scapi.SoundCloudAPI(host='localhost:8080')

    #user = scapi.User.new(user_name="name", password="password", display_name="display_name", email_address="email_address")
    #assert isinstance(user, scapi.User)
    sca = scapi.Scope()
    all_users = sca.users()
    logger.debug(all_users)
    assert isinstance(all_users, list) and isinstance(all_users[0], scapi.User)
    user = sca.me()
    logger.debug(user)
    assert isinstance(user, scapi.User)
    contacts = user.contacts()
    assert isinstance(contacts, list)
    assert isinstance(contacts[0], scapi.User)
    logger.debug(contacts)
    tracks = user.tracks()
    assert isinstance(tracks, list)
    assert isinstance(tracks[0], scapi.Track)
    logger.debug(tracks)


def test_access_token_acquisition():
    """
    This test is commented out because it needs user-interaction.
    """
    if not RUN_INTERACTIVE_TESTS:
        return
    oauth_authenticator = scapi.authentication.OAuthAuthenticator(CONSUMER, 
                                                                  CONSUMER_SECRET,
                                                                  None, 
                                                                  None)

    sca = scapi.SoundCloudAPI(host=API_HOST, authenticator=oauth_authenticator)
    token, secret = sca.fetch_request_token()
    authorization_url = sca.get_request_token_authorization_url(token)
    webbrowser.open(authorization_url)
    raw_input("please press return")
    oauth_authenticator = scapi.authentication.OAuthAuthenticator(CONSUMER, 
                                                                  CONSUMER_SECRET,
                                                                  token, 
                                                                  secret)

    sca = scapi.SoundCloudAPI(API_HOST, authenticator=oauth_authenticator)
    token, secret = sca.fetch_access_token()

    oauth_authenticator = scapi.authentication.OAuthAuthenticator(CONSUMER, 
                                                                  CONSUMER_SECRET,
                                                                  token, 
                                                                  secret)

    sca = scapi.SoundCloudAPI(API_HOST, authenticator=oauth_authenticator)
    test_track_creation()

def test_track_creation():
    track = scapi.Track.new(title='bar')
    assert isinstance(track, scapi.Track)

def test_track_update():
    track = scapi.Track.new(title='bar')
    assert isinstance(track, scapi.Track)
    track.title='baz'
    track = scapi.Track.get(track.id)
    assert track.title == "baz"

def test_scoped_track_creation():
    sca = scapi.Scope()
    user = sca.me()
    track = user.tracks.new(title="bar")
    assert isinstance(track, scapi.Track)

def test_upload():
    assert pkg_resources.resource_exists("scapi.tests.test_connect", "knaster.mp3")
    data = pkg_resources.resource_stream("scapi.tests.test_connect", "knaster.mp3")
    sca = scapi.Scope()
    user = sca.me()
    logger.debug(user)

    asset = sca.assets.new(filedata=data)
    assert isinstance(asset, scapi.Asset)
    logger.debug(asset)
    tracks = user.tracks()
    track = tracks[0]
    track.assets.append(asset)

def test_contact_list():
    sca = scapi.Scope()
    user = sca.me()
    contacts = user.contacts()
    assert isinstance(contacts, list)
    assert isinstance(contacts[0], scapi.User)

def test_permissions():
    sca = scapi.Scope()
    user = sca.me()
    tracks = user.tracks()
    logger.debug("Found %i tracks", len(tracks))
    for track in tracks[:1]:
        permissions = track.permissions()
        logger.debug(permissions)
        assert isinstance(permissions, list)
        if permissions:
            assert isinstance(permissions[0], scapi.User)

def test_setting_permissions():
    sca = scapi.Scope()
    me = sca.me()
    track = scapi.Track.new(title='bar', sharing="private")
    assert track.sharing == "private"
    users = sca.users()
    users_to_set = [user  for user in users[:10] if user != me]
    assert users_to_set, "Didn't find any suitable users"
    track.permissions = users_to_set
    assert set(track.permissions()) == set(users_to_set)

def test_setting_comments():
    assert pkg_resources.resource_exists("scapi.tests.test_connect", "knaster.mp3")
    data = pkg_resources.resource_stream("scapi.tests.test_connect", "knaster.mp3")
    sca = scapi.Scope()
    user = sca.me()
    track = scapi.Track.new(title='bar', sharing="private")
    comment = scapi.Comment.create(body="This is the body of my comment", timestamp=10)
    track.comments = comment
    assert track.comments()[0].body == comment.body
    

def test_setting_comments_the_way_shawn_says_its_correct():
    sca = scapi.Scope()
    user = sca.me()
    track = scapi.Track.new(title='bar', sharing="private")
    #comment = scapi.Comment.create(body="This is the body of my comment", timestamp=10)
    cbody = "This is the body of my comment"
    track.comments.new(body=cbody, timestamp=10)
    assert track.comments()[0].body == cbody

def test_contact_add_and_removal():
    sca = scapi.Scope()
    me = sca.me()
    users = sca.users()
    for user in users[:10]:
        if user != me:            
            user_to_set = user
            break

    contacts = me.contacts()
    contacts = contacts if contacts is not None else []

    if user_to_set in contacts:
        me.contacts.remove(user_to_set)

    me.contacts.append(user_to_set)

    contacts = me.contacts() 
    contacts = contacts if contacts is not None else []

    assert user_to_set.id in [c.id for c in contacts]

    me.contacts.remove(user_to_set)

    contacts = me.contacts() 
    contacts = contacts if contacts is not None else []

    assert user_to_set not in contacts


def test_favorites():
    sca = scapi.Scope()
    me = sca.me()

    favorites = me.favorites()    
    favorites = favorites if favorites is not None else []    

    if favorites:
        assert isinstance(favorites[0], scapi.Track)

    for user in sca.users():
        if user == me:
            continue
        tracks = user.tracks()
        if tracks:
            track = tracks[0]
            break
    
    me.favorites.append(track)

    favorites = me.favorites()    
    favorites = favorites if favorites is not None else []    

    assert track in favorites

    me.favorites.remove(track)

    favorites = me.favorites()    
    favorites = favorites if favorites is not None else []    

    assert track not in favorites

    

def test_large_list():
    sca = scapi.Scope()
    tracks = list(sca.tracks())
    if len(tracks) < scapi.SoundCloudAPI.LIST_LIMIT:
        for i in xrange(scapi.SoundCloudAPI.LIST_LIMIT):            
            scapi.Track.new(title='test_track_%i' % i)
    all_tracks = sca.tracks()
    assert not isinstance(all_tracks, list)
    all_tracks = list(all_tracks)
    assert len(all_tracks) > scapi.SoundCloudAPI.LIST_LIMIT


def test_auth():
    sca = scapi.Scope()
    me = sca.me()



def test_events():
    sca = scapi.Scope()
    user = sca.me()
    events = sca.events()
    assert isinstance(events, list)
    assert isinstance(events[0], scapi.Event)


def test_me_having_stress():
    sca = scapi.Scope()
    for _ in xrange(20):
        setup()
        sca.me()


