# File: app.py

import os
import requests
import json
import redis
import polyline
import time


from flask import Flask, request, jsonify

app = Flask(__name__)
REDIS_URL = os.environ.get('REDIS_URL')
STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
STRAVA_VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.environ.get('GITHUB_REPO_OWNER')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPO_NAME')
GITHUB_EVENT_TYPE = os.environ.get('GITHUB_EVENT_TYPE')


r = redis.Redis.from_url(REDIS_URL)

def get_tokens():
    """Reads tokens from a simple key-value store."""
    try:
        tokens = r.get('strava_tokens')
        if tokens:
            return json.loads(tokens)
    except Exception as e:
        print(f"Error retrieving tokens from KV store: {e}")
    
    # Fallback to initial environment variables if KV store is empty
    initial_tokens = {
        'access_token': os.environ.get('STRAVA_INITIAL_ACCESS_TOKEN'),
        'refresh_token': os.environ.get('STRAVA_INITIAL_REFRESH_TOKEN')
    }
    return initial_tokens

def save_tokens(tokens):
    """Saves tokens to a simple key-value store."""
    try:
        r.set('strava_tokens', json.dumps(tokens))
    except Exception as e:
        print(f"Error saving tokens to KV store: {e}")

def refresh_access_token(refresh_token):
    """Refreshes the access token using the refresh token."""
    token_url = "https://www.strava.com/oauth/token"
    data = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    new_tokens = response.json()
    save_tokens(new_tokens)
    return new_tokens.get('access_token')

@app.route('/strava_webhook', methods=['GET', 'POST'])
def strava_webhook():
    # Handle the GET request for subscription validation
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode == 'subscribe' and token == STRAVA_VERIFY_TOKEN:
            print("Webhook subscription validated.")
            return jsonify({'hub.challenge': challenge})
        else:
            print("Webhook verification failed.")
            return "Forbidden", 403

    # Handle the POST request for activity events
    if request.method == 'POST':
        payload = request.get_json()
        print("Received Strava webhook:", payload)
        
        # Acknowledge the webhook immediately to avoid retries
        # A quick response is required by Strava
        response_data = {"status": "success"}
        
        # Process the webhook in a separate thread or background task
        # This is highly recommended to return a quick 200 response to Strava.
        # For simplicity, we'll do the request directly, but be aware of timeouts.
        
        # Trigger the GitHub Action
        if payload.get('aspect_type') == 'create' and payload.get('object_type') == 'activity':

            activity_id = payload.get('object_id')
            owner_id = payload.get('owner_id')

            # Get the access token, refreshing it if necessary

            tokens = get_tokens()
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token')
            expires_at = tokens.get('expires_at')

            if not access_token or (expires_at and expires_at < time.time()):
                if refresh_token:
                    access_token = refresh_access_token(refresh_token)
                else:
                    print("No refresh token available. Manual re-authorization is required.")
                    return jsonify(response_data), 200

            # Get full activity data from Strava API
            try:
                activity_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
                headers = {'Authorization': f'Bearer {access_token}'}
                
                
                strava_response = requests.get(activity_url, headers=headers)
                strava_response.raise_for_status()
                activity_data = strava_response.json()
                print(f"Successfully fetched activity data for ID {activity_id}")
                

                # Decode the polyline and add it to the data
                polyline_string = activity_data['map']['summary_polyline']
                decoded_polyline = polyline.decode(polyline_string)
                
                # Filter activity data to only include name, distance, sport_type, and decoded polyline
                filtered_activity_data = {
                    "name": activity_data.get("name"),
                    "distance": activity_data.get("distance"),
                    "sport_type": activity_data.get("sport_type"),
                    "decoded_polyline": decoded_polyline
                }

                github_api_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches"
                
                headers = {
                    'Accept': 'application/vnd.github+json',
                    'Authorization': f'token {GITHUB_TOKEN}'
                }
                
                data = {
                    "event_type": GITHUB_EVENT_TYPE,
                    "client_payload": {
                        "activity_id": activity_id,
                        "owner_id": owner_id,
                        "activity_data": filtered_activity_data
                    }
                }
            
            
                github_response = requests.post(github_api_url, headers=headers, json=data)
                github_response.raise_for_status() # Raise an exception for bad status codes
                print(f"Successfully triggered GitHub Action with activity ID: {payload.get('object_id')}")
            except requests.exceptions.RequestException as e:
                print(f"Failed to trigger GitHub Action: {e}")

        # Always return a 200 status to Strava to acknowledge receipt
        return jsonify(response_data), 200

# To run the app locally, you would add:
# if __name__ == '__main__':
#     app.run(port=5000)