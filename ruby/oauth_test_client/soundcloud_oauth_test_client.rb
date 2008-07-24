#### SoundCloud OAuth tester
#
# Author: Hannes Tydén, hannes@soundcloud.com
# Last modified: 2008-07-24
# 
# This is a small ruby hack to test the SoundCloud API with OAuth authentication.
# It is thought to be used in irb.
# 
### How to:
#
# Configure the consumer and token data below
# Start irb:
# $ irb
# Load the test client script:
# >> require 'oauth_client.rb'
# If you haven't got an access token
# >> get_access_token
# Get to know yourself:
# >> who_am_i
#
### Available commands:
#
## Tokens:
# >> get_access_token
# >> use_saved_access_token
# >> use_invalid_access_token
# >> use_with_invalid_secret
#
## Requests
# >> test_request
# >> who_am_i
# >> get_user_tracks
# >> get_tracks
# >> get_track
# >> post_track_comment

### Setup
# This is where you configure the client to work with your specific settings

# Your consumer application
@consumer_application = {:key => 'Consumer key', :secret => 'Consumer secret'}

# If you already have an authorized token and don't want to negotiate a new.
@saved_access_token = {:key => 'Token key', :secret => 'Token secret'}

# If you want to test the security by trying to access protected resources with an invalid token.
@invalid_access_token = {:key => 'Invalid token key', :secret => 'Token secret'}

# If you want to test the security by trying to access protected resources with an invalid token secret.
@token_with_invalid_secret = {:key => 'Token key', :secret => 'Invalid token secret'}

require 'rubygems'
require 'json'
# Generic setup
gem 'oauth', '0.2.2'
require 'oauth/consumer'

def reload!
  puts "Reloading '#{__FILE__}'"
  load __FILE__
end

class String
  def blank?
    self.nil? || self.strip == ""
  end
end

@consumer = OAuth::Consumer.new @consumer_application[:key], @consumer_application[:secret], {
  :site               => 'http://api.sandbox-soundcloud.com', 
  :request_token_path => '/oauth/request_token',
  :access_token_path  => '/oauth/access_token',
  :authorize_path     => '/oauth/authorize'
}

@authorize_url = 'http://sandbox-soundcloud.com/oauth/authorize?oauth_token='

def use_saved_access_token
  @access_token = OAuth::AccessToken.new(@consumer, @saved_access_token[:key], @saved_access_token[:secret])
end

def use_access_token_with_invalid_secret
  @access_token = OAuth::AccessToken.new(@consumer, @token_with_invalid_secret[:key], @token_with_invalid_secret[:secret])
end

def use_invalid_access_token
  @access_token = OAuth::AccessToken.new(@consumer, @invalid_access_token[:key], @invalid_access_token[:secret])
end

def get_access_token
  # Get request token
  puts "Get request token"
  request_token = @consumer.get_request_token

  # Goto URL and authorize token
  puts "Press enter to open a browser, log in to SoundCloud and authorize this application."
  gets
  `open "#{@authorize_url + request_token.token}"`
  puts "Press enter when request token is authorized."
  gets

  # When request token is authorized, get access token
  @access_token = request_token.get_access_token
  if test_request.code == '200'
    puts "Access granted."
    @access_token
  else
    puts "Access denied."
  end
  
  rescue Net::HTTPServerException => e
    puts "Error: #{e}"
end

def form_urlencode(hash)
  hash.map { |(key, value)| "#{key}=#{value}" }.join("&")
end

def build_options(options)
  default_options = {:params => {}, :headers => {'Accept' => "application/json"}}
  default_options.merge(options)
end

def test_request(options = {})
  options = build_options options
  params = '?' + form_urlencode(options[:params])
  headers = options[:headers]
  puts "Test request: params => #{params}, headers => #{headers}"
  response = @access_token.get("/oauth/test_request#{params}", headers)
  puts "Test response: code => #{response.code}, body => #{response.body}"
  response
end

def who_am_i(options = {})
  options = build_options options
  headers = options[:headers]
  response = @access_token.get('/me/', headers)
  unless response.body.blank?
    JSON.parse(response.body)
  else
    puts "Could not find."
  end
end 

def get_user_tracks(user_id, options = {})
  options = build_options options
  params = '?' + form_urlencode(options[:params])
  headers = options[:headers]
  response = @access_token.get("/users/#{user_id}/tracks#{params}", headers)
  unless response.body.blank?
    JSON.parse(response.body)
  else
    puts "Could not find."
  end
end 

def get_tracks(options = {})
  options = build_options options
  params = '?' + form_urlencode(options[:params]) if options[:params]
  headers = options[:headers]
  response = @access_token.get("/tracks#{params}", headers)
  unless response.body.blank?
    JSON.parse(response.body)
  else
    puts "Could not find."
  end
end

def get_track(track_id, options = {})
  options = build_options options
  params = '?' + form_urlencode(options[:params])
  headers = options[:headers]
  response = @access_token.get("/tracks/#{track_id}#{params}", headers)
  unless response.body.blank?
    JSON.parse(response.body)
  else
    puts "Could not find."
  end
end

def post_track_comment(track_id, comment_body, options = {})
  options = build_options options
  params = '?' + form_urlencode(options[:params])
  headers = options[:headers]
  body = {'comment[body]' => comment_body}
  response = @access_token.post("/tracks/#{track_id}/comments#{params}", body, headers)
  unless response.body.blank?
    JSON.parse(response.body)
  else
    puts response.headers.inspect
  end
end