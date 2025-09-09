# File: app.py

import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Load environment variables
STRAVA_VERIFY_TOKEN = os.environ.get('STRAVA_VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO_OWNER = os.environ.get('GITHUB_REPO_OWNER')
GITHUB_REPO_NAME = os.environ.get('GITHUB_REPO_NAME')
GITHUB_EVENT_TYPE = os.environ.get('GITHUB_EVENT_TYPE')

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
            github_api_url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches"
            
            headers = {
                'Accept': 'application/vnd.github+json',
                'Authorization': f'token {GITHUB_TOKEN}'
            }
            
            data = {
                "event_type": GITHUB_EVENT_TYPE,
                "client_payload": {
                    "activity_id": payload.get('object_id'),
                    "owner_id": payload.get('owner_id')
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