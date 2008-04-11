import pkg_resources
import scapi
import scapi.authentication
import logging
import webbrowser

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
#_logger = logging.getLogger("scapi.authentication")
#_logger.setLevel(logging.DEBUG)

TOKEN  = "CVnhk6fBIxSwLc8Bwdr8g"
SECRET = "oSb0ZAwJusUy3iM7OJ5dj6tyTu5deSw9AeuT5OslU"
CONSUMER = "Cy2eLPrIMp4vOxjz9icdQ"
CONSUMER_SECRET = "KsBa272x6M2to00Vo5FdvZXt9kakcX7CDIPJoGwTro"
API_HOST = 'api.soundcloud.dev:3000'

def setup():
    #scapi.SoundCloudAPI(host='192.168.2.101:3000', user='tiga', password='test')
    #scapi.SoundCloudAPI(host='staging-api.soundcloud.com:3030', user='tiga', password='test')
    scapi.USE_PROXY = True
    scapi.PROXY = 'http://127.0.0.1:10000/'

    oauth_authenticator = scapi.authentication.OAuthAuthenticator(CONSUMER, 
                                                                  CONSUMER_SECRET,
                                                                  TOKEN, 
                                                                  SECRET)
    basic_authenticator = scapi.authentication.BasicAuthenticator('tiga', 'test', CONSUMER, CONSUMER_SECRET)
    scapi.SoundCloudAPI(host=API_HOST, 
                        authenticator=oauth_authenticator)
                        #authenticator=basic_authenticator)
    
def test_connect():
    #sca = scapi.SoundCloudAPI(host='localhost:8080')

    #user = scapi.User.new(user_name="name", password="password", display_name="display_name", email_address="email_address")
    #assert isinstance(user, scapi.User)
    sca = scapi.Scope()
    all_users = sca.users()
    print all_users
    assert isinstance(all_users, list) and isinstance(all_users[0], scapi.User)
    user = sca.me()
    print user
    assert isinstance(user, scapi.User)
    contacts = user.contacts()
    assert isinstance(contacts, list)
    assert isinstance(contacts[0], scapi.User)
    print contacts

    tracks = user.tracks()
    assert isinstance(tracks, list)
    assert isinstance(tracks[0], scapi.Track)
    print tracks


def test_access_token_acquisition():
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
    assert pkg_resources.resource_exists("tests.test_connect", "knaster.mp3")
    data = pkg_resources.resource_stream("tests.test_connect", "knaster.mp3")
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
    assert pkg_resources.resource_exists("tests.test_connect", "knaster.mp3")
    data = pkg_resources.resource_stream("tests.test_connect", "knaster.mp3")
    sca = scapi.Scope()
    user = sca.me()
    track = scapi.Track.new(title='bar', sharing="private")
    comment = scapi.Comment.create(body="This is the body of my comment", timestamp=10)
    track.comments = comment
    assert track.comments()[0].body == comment.body
    
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
    me = sca.me()
    tracks = sca.tracks()
    if len(tracks) < scapi.SoundCloudAPI.LIST_LIMIT:
        for i in xrange(scapi.SoundCloudAPI.LIST_LIMIT):            
            track = scapi.Track.new(title='test_track_%i' % i)
    all_tracks = sca.tracks()
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
        user = sca.me()
