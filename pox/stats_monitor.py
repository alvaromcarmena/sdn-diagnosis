# author: 2013 Oscar Araque 
# Version 2.0: Alvaro Martinez Carmena
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A skeleton POX component

You can customize this to do whatever you like.  Don't forget to
adjust the Copyright above, and to delete the Apache license if you
don't want to release under Apache (but consider doing so!).

Rename this file to whatever you like, .e.g., mycomponent.py.  You can
then invoke it with "./pox.py mycomponent" if you leave it in the
ext/ directory.

Implement a launch() function (as shown below) which accepts commandline
arguments and starts off your component (e.g., by listening to events).

Edit this docstring and your launch function's docstring.  These will
show up when used with the help component ("./pox.py help --mycomponent").
"""

# Import some POX stuff
from pox.core import core                     # Main POX object
import pox.openflow.libopenflow_01 as of      # OpenFlow 1.0 library
import pox.lib.packet as pkt                  # Packet parsing/construction
from pox.lib.addresses import EthAddr, IPAddr # Address types
import pox.lib.util as poxutil                # Various util functions
import pox.lib.revent as revent               # Event library
import pox.lib.recoco as recoco               # Multitasking library
from pox.lib.util import dpid_to_str
from pox.openflow.of_json import *

import multiprocessing
import json

# Create a logger for this component
log = core.getLogger("Monitor")

# Create a global var to portStatus method


def _send_to_pipe(data):
    with open('/dev/shm/poxpipe','w') as pipe:
        pipe.write(data)

def _to_pipe(data):
    p = multiprocessing.Process(target=_send_to_pipe, args=(data,))
    p.start()

def _go_up (event):
    # Event handler called when POX goes into up state
    # (we actually listen to the event in launch() below)
    log.info("Monitor application ready.")

def _request_stats():
    log.debug('Number of connections: {}'.format(len(core.openflow.connections)))
    log.info('Sending stats requests')
    for connection in core.openflow.connections:
        log.debug("Sending stats request")
        #connection.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
        connection.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        #connection.send(of.ofp_stats_request(body=of.ofp_queue_stats_request()))

def _handle_flowstats(event):
    log.info(event.stats)
    stats = flow_stats_to_list(event.stats)
    dpid = poxutil.dpidToStr(event.connection.dpid)
    log.debug('Received flow stats from {}'.format(dpid))
    data = {'type': 'switch_flowstats', 'data': {'switch': dpid, 'stats': stats}}
    log.debug(data)
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)

def _handle_portstats(event):
    stats = flow_stats_to_list(event.stats)
    #log.info(stats)
    dpid = poxutil.dpidToStr(event.connection.dpid)
    log.debug('Received port stats from {}'.format(dpid))
    data = {'type':"switch_portstats", "data":{'switch':dpid, 'stats':stats}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)

def _handle_LinkEvent(event):
    is_up = event.added is True and event.removed is False
    link = event.link.end
    data = {'type': 'linkstats', 'data': {'link':link, 'up': is_up}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)

def _handle_queuestats(event):
    stats = flow_stats_to_list(event.stats)
    log.info(stats)
    dpid = poxutil.dpidToStr(event.connection.dpid)
    log.debug('Received queue stats from {}'.format(dpid))
    data = {'type':"switch_queuestats", "data":{'switch':dpid, 'stats':stats}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)

def _handle_ConnectionDown (event):
    log.info("Switch %s has come down.", dpid_to_str(event.dpid))
    dpid = dpid_to_str(event.dpid)
    data = {'type':"switch_down", "data":{'switch':dpid, 'down': True}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)


def _handle_ConnectionUp (event):
    log.info("Switch %s has come up.", dpid_to_str(event.dpid))
    dpid = dpid_to_str(event.dpid)
    data = {'type':"switch_down", "data":{'switch':dpid, 'down': False}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)

def _handle_PortStatus (event):
    if event.added:
        action = "added"
    elif event.deleted:
        action = "removed"
    else:       
        action = "modified"
        
    dpid = dpid_to_str(event.dpid)
    data = {'type':"port_status", "data":{'switch':dpid, 'portdown':{'port':event.port, 'action':action}}}
    data = json.dumps(data)
    data += '#'
    _to_pipe(data)
    print "Port %s on Switch %s has been %s." % (event.port, event.dpid, action)

@poxutil.eval_args
def launch (bar = False):
    """
    The default launcher just logs its arguments
    """
    log.warn("Bar: %s (%s)", bar, type(bar))

    core.addListenerByName("UpEvent", _go_up)
    core.openflow_discovery.addListenerByName("LinkEvent", _handle_LinkEvent)
    #core.openflow.addListenerByName("FlowStatsReceived", _handle_flowstats)
    core.openflow.addListenerByName("PortStatsReceived", _handle_portstats)    
    #core.openflow.addListenerByName("QueueStatsReceived", _handle_queuestats)
    core.openflow.addListenerByName("ConnectionDown", _handle_ConnectionDown)
    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    core.openflow.addListenerByName("PortStatus", _handle_PortStatus)
    recoco.Timer(7, _request_stats, recurring=True)
