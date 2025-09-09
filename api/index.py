# File: app.py

import os
import requests
import json

from flask import Flask, request, jsonify

TOKEN_FILE = 'strava_tokens.json'


app = Flask(__name__)

STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
STRAVA_VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.environ.get('GITHUB_REPO_OWNER')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPO_NAME')
GITHUB_EVENT_TYPE = os.environ.get('GITHUB_EVENT_TYPE')

def get_tokens():
    """Reads tokens from a file."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    """Saves tokens to a file."""
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f, indent=4)

def refresh_strava_token(refresh_token):
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

            tokens = get_tokens()
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token')

            # Step 1: Fetch the full activity data from the Strava API
            strava_api_url = f"https://www.strava.com/api/v3/activities/{activity_id}"

            for attempt in range(2):
                headers = {'Authorization': f'Bearer {access_token}'}
                
                try:
                    strava_response = requests.get(strava_api_url, headers=headers)
                    strava_response.raise_for_status()
                    activity_data = strava_response.json()
                    print(f"Successfully fetched activity data for ID {activity_id}")
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401 and attempt == 0:
                        print("Access token expired. Attempting to refresh.")
                        access_token = refresh_strava_token(refresh_token)
                    else:
                        raise e                
                except requests.exceptions.RequestException as e:
                    print(f"Failed to fetch Strava activity data: {e}")
                    # If fetching fails, we still proceed to trigger the GitHub Action with a limited payload
                    activity_data = {"error": f"Failed to fetch activity details: {e}"}


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
                    "activity_data": activity_data
                }
            }
            
            try:
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