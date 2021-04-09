import requests
import json
import os
import re
import boto3
# from slack_sdk import WebClient
# from slack_sdk.errors import SlackApiError

###################################################
#
# Lambda function to handle slack webhooks
#
###################################################
slack_token = os.environ['SLACK_TOKEN']
verification_token = os.environ['SLACK_VERIFICATION_CODE']
subscriptions_table_name = os.environ['SUBSCRIPTIONS_TABLE_NAME']

# slackClient = WebClient(token=slack_token)

def webhook_handler(event, context):
    try:
        if not slack_token:
            raise Exception("mentionbot:slack_token was not provided")
        if not verification_token:
            raise Exception("mentionbot:verification_token was not provided")
        if not subscriptions_table_name:
            raise Exception("mentionbot:subscriptions_table_name was not provided")

        request = json.loads(event['body'])

        print('Parsed request...')
        print(request)
        if request['type'] == "url_verification":
            # url_verification is the simple message slack sends to our endpoint to
            # just make sure we're setup properly.  All we have to do is get the
            # challenge data they send us and return it untouched.
            challenge = request["challenge"]
            
            return {
                "statusCode": 200,
                "body": json.dumps({"challenge": challenge})
            }

        elif request["type"] == 'event_callback':
            if request["token"] != verification_token:
                print("Error: Invalid verification token")
                
                return { 
                    "statusCode": 401,
                    "body": "Invalid verification token"
                }

            else:
                on_event_callback(request)
        else:
            print("Unknown event type: " + request.type)
    except Exception as err:
        print('Error processing this request')
        print(err)
        print(event)
        # Fall through. Even in the event of an error, we want to return '200' so that slack
        # doesn't just repeat the message, causing the same error.

        # Always return success so that Slack doesn't just immediately resend this message to us.
        return { "statusCode": 200, "body": err }

# [x] First Draft Completed
# [ ] Tested
def on_event_callback(request):
    print('request event')
    print(request['event'])
    event = request["event"]

    if "message" == event["type"]:
        print('event_type: message')
        on_message_event_callback(event)
    elif "app_mention" == event["type"]:
        print('event_type: app_mention')
        on_app_mention_event_callback(event)
    else:
        print("Unknown event type: " + event['type'])

def process_match(event, match):
    # Remove the <@ and > tags to grab the username / id
    id = match[len("<@"):len(match)-len(">")]
    client = boto3.client('dynamodb')
    resp = client.get_item(
        TableName = subscriptions_table_name,
        Key = {
            "id": {
                "S": id
            }
        }
    )

    print('Get  match response')
    print(resp)

    if not resp:
        return
    
    perma_link = get_permalink(channel=resp["Item"]["channel"], timestamp=event['event_ts'])
    
    print('perma_link')
    print(perma_link)

    message = 'New mention at ' + perma_link
    send_channel_message(resp["Item"]["channel"], message)

# [] written
# [] Tested
def on_message_event_callback(event):
    if not event['text']:
        print("No text in message.")
        # No text for the message, so nothing to do.
        return

    print(event["text"])
    # find all values that match the shape <@ **** >
    search = re.compile(r"<@(.*?)>")
    matches = search.findall(event["text"])

    if not matches:
        print('No matches found')
        # No @mentions in the message, so nothing to do.
        return

    # There might be multiple @mentions to the same person in the same message.
    # So make into a set to make things unique.
    for match in list(set(matches)):
        print("Process match")
        process_match(
            event=event, 
            match=match)

# sendChannelMessage
# [ ] first draft
# [ ] tested
def send_channel_message(channel, text):
    message = { "channel": channel, "text": text}

    print("Sending channel message")
    print(message)

    # response = slackClient.chat_postMessage(channel=channel, text=text)
    # r = requests.get('https://slack.com/api/chat.sendMessage?' + json.dumps(message))
    r = requests.post(
        'https://slack.com/api/chat.postMessage?',
        data=json.dumps(message),
        headers={
            "Authorization": "Bearer " + slack_token,
            "Content-Type": "application/json"
        }
    )

    resp = r.json()
    print('Send message response')
    print(resp)

def get_permalink(channel, timestamp):
    message = { "token": slack_token, "channel": channel, "message_ts": timestamp }
    # TODO: Requires url encoding and can't accept posts
    r = requests.get('https://slack.com/api/chat.getPermalink?' + json.dumps(message))
    return r.json().permalink

def on_app_mention_event_callback(event):
    if "unsubscribe" in event["text"].lower():
        print("Unsubscribing user")
        unsubscribe_from_mentions(event)
    else:
        print("Subscribing user")
        subscribe_to_mentions(event)

# async function onAppMentionEventCallback(request: EventCallbackRequest) {
#     // Got an app_mention to @mentionbot.
#     const event = request.event;
#     const promise = event.text.toLowerCase().indexOf("unsubscribe") >= 0
#         ? unsubscribeFromMentions(event)
#         : subscribeToMentions(event);

#     return await promise;
# }

def unsubscribe_from_mentions(event):
    client = boto3.client('dynamodb')
    client.delete_item(
        TableName = subscriptions_table_name,
        Key = {
            "id": {
                "S": event['user']
            }
        }
    )
    text = "Hi <@" + event['user'] + ">. You've been unsubscribed from @ mentions. Mention me again to resubscribe."
    send_channel_message(event['channel'], text)

def subscribe_to_mentions(event):
    channel = event['channel']
    print(channel)
    dynamodb_client = boto3.client('dynamodb')
    dynamodb_client.put_item(
        TableName = subscriptions_table_name,
        Item = {
            "id": {
                "S": event['user'],
            },
            "channel": {
                "S": event['channel']
            }
        }
    )
    text = "Hi <@"+event['user']+">. You've been subscribed to @ mentions. Send me a message containing 'unsubscribe' to stop receiving those notifications."
    
    print(text)
    send_channel_message(event['channel'], text)