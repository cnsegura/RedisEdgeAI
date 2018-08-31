# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import random
import time
import sys
import redis
import json
import pygal
import iothub_client
# pylint: disable=E0611
from iothub_client import IoTHubModuleClient, IoTHubClientError, IoTHubTransportProvider
from iothub_client import IoTHubMessage, IoTHubMessageDispositionResult, IoTHubError

from flask import Flask, render_template
app = Flask(__name__)

@app.route('/')
def index():

    # Initialize Redis DB connection
    r = redis.Redis(host='redisedge', port=6379)

    endtsfloat = time.time() *1000
    endts = int(float(endtsfloat)) 
    endtsstr = str(endts)
    #print('\n****\nendts string is: ')
    #print(endtsstr)
    starttsstr = str((endts - 30000))
    
    ####
    # get apple data
    ####

    #look up last 30 seconds of data
    xrangestring = 'XRANGE appleStream ' + starttsstr + ' ' + endtsstr
    print('\n****\nRange string is: ')
    print(xrangestring)
    streamvalue = r.execute_command(xrangestring)
    
    #create x/y for apple chart
    xAxis = [item[0][:-2] for item in streamvalue]
    #debug
    #print('\n******\nxAxis is : ')
    #print(xAxis)
    yAxis = [float(item[1][3]) for item in streamvalue]
    isApple = sum(i > 0.8 for i in yAxis)
    isNotApple = sum(j < 0.2 for j in yAxis)
    isMaybeApple = sum(k < 0.8 and k > 0.2 for k in yAxis)
    isAppleCount = {'isApple': isApple}
    isNotAppleCount = {'isNotApple': isNotApple}
    isMaybeAppleCount = {'isMaybeApple': isMaybeApple}
    #debug
    #print('\n******\nyAxis is : ')
    #print(yAxis)
    #print('\n******\nRedis streamvalue is : ')
    #print(streamvalue)

    #build apple chart
    applebar_chart =  pygal.Bar(title =u'Apples - last 30s', width = 500, size = 300, explicit_size = True)
    applebar_chart.x_labels = xAxis
    applebar_chart.add('Apples', yAxis)

    #####
    #get banana data
    #####
    xrangestring = None
    streamvalue[:] = []
    #xAxis[:] =[]
    #yAxis[:] = []

    xrangestring = 'XRANGE bananaStream ' + starttsstr + ' ' + endtsstr
    streamvalue = r.execute_command(xrangestring)
    print('\n****\nRange string is: ')
    print(xrangestring)
    #create x/y for banana chart 
    xAxisB = [item[0][:-2] for item in streamvalue]
    yAxisB = [float(item[1][3]) for item in streamvalue]
    isBanana = sum(i > 0.8 for i in yAxisB)
    isNotBanana = sum(j < 0.2 for j in yAxisB)
    isMaybeBanana = sum(k < 0.8 and k > 0.2 for k in yAxisB)
    isBananaCount = {'isBanana': isBanana}
    isNotBananaCount = {'isNotBanana': isNotBanana}
    isMaybeBananaCount = {'isMaybeBanana': isMaybeBanana}

    bananabar_chart =  pygal.Bar(title =u'Bananas - last 30s', width = 500, size = 300, explicit_size = True)
    bananabar_chart.x_labels = xAxisB
    bananabar_chart.add('Bananas', yAxisB)

    #generate graphs
    #context = {}
    #context[u'applebar_chart'] = applebar_chart
    #context[u'isApple'] = isApple
    #context[u'bananabar_chart'] = bananabar_chart

    return render_template('index.html', isAppleCount=isAppleCount, isNotAppleCount=isNotAppleCount, isMaybeAppleCount=isMaybeAppleCount, applebar_chart=applebar_chart, isBananaCount=isBananaCount, isNotBananaCount=isNotBananaCount, isMaybeBananaCount=isMaybeBananaCount, bananabar_chart=bananabar_chart)

# messageTimeout - the maximum time in milliseconds until a message times out.
# The timeout period starts at IoTHubModuleClient.send_event_async.
# By default, messages do not expire.
MESSAGE_TIMEOUT = 10000

# global counters
RECEIVE_CALLBACKS = 0
SEND_CALLBACKS = 0

# Choose HTTP, AMQP or MQTT as transport protocol.  Currently only MQTT is supported.
PROTOCOL = IoTHubTransportProvider.MQTT

# Callback received when the message that we're forwarding is processed.
def send_confirmation_callback(message, result, user_context):
    global SEND_CALLBACKS
    print ( "Confirmation[%d] received for message with result = %s" % (user_context, result) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    SEND_CALLBACKS += 1
    print ( "    Total calls confirmed: %d" % SEND_CALLBACKS )


# receive_message_callback is invoked when an incoming message arrives on the specified 
# input queue (in the case of this sample, "input1").  Because this is a filter module, 
# we will forward this message onto the "output1" queue.
def receive_message_callback(message, hubManager):
    global RECEIVE_CALLBACKS
    message_buffer = message.get_bytearray()
    size = len(message_buffer)
    print ( "    Data: <<<%s>>> & Size=%d" % (message_buffer[:size].decode('utf-8'), size) )
    map_properties = message.properties()
    key_value_pair = map_properties.get_internals()
    print ( "    Properties: %s" % key_value_pair )
    RECEIVE_CALLBACKS += 1
    print ( "    Total calls received: %d" % RECEIVE_CALLBACKS )
    hubManager.forward_event_to_output("output1", message, 0)
    return IoTHubMessageDispositionResult.ACCEPTED

class HubManager(object):

    def __init__(
            self,
            protocol=IoTHubTransportProvider.MQTT):
        self.client_protocol = protocol
        self.client = IoTHubModuleClient()
        self.client.create_from_environment(protocol)

        # set the time until a message times out
        self.client.set_option("messageTimeout", MESSAGE_TIMEOUT)
        
        # sets the callback when a message arrives on "input1" queue.  Messages sent to 
        # other inputs or to the default will be silently discarded.
        self.client.set_message_callback("input1", receive_message_callback, self)

    # Forwards the message received onto the next stage in the process.
    def forward_event_to_output(self, outputQueueName, event, send_context):
        self.client.send_event_async(
            outputQueueName, event, send_confirmation_callback, send_context)

def main(protocol):
    try:
        hub_manager = HubManager(protocol)
        
        print ( "Starting the webserver at localhost ")
        # Run the server
        app.run(host='0.0.0.0', port=8080)

    except IoTHubError as iothub_error:
        print ( "Unexpected error %s from IoTHub" % iothub_error )
        return
    except KeyboardInterrupt:
        print ( "IoTHubModuleClient sample stopped" )

if __name__ == '__main__':
    main(PROTOCOL)