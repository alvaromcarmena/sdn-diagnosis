import multiprocessing
import json
import time
import sys
import re
import logging
from collections import defaultdict
from jinja2 import Template
from scipy.interpolate import spline
from scipy.signal import butter, lfilter
import numpy as np
import csv, operator
from jpype import *
import jpype

"""
stats = {
    'switches': defaultdict(dict)
}
"""
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

low_limit = 100
high_limit = 3000
dpid_p = "00-00-00-00-00-02"
dpid_p2 = "00-00-00-00-00-03"


def _create_csv():
    csvsalida = open('netstats.csv', 'w', newline='')
    salida = csv.writer(csvsalida)
    salida.writerow(['rx_packets_level', 'tx_packets_level', 'lost_packets_level', 'eth1-up', 'eth2-up', 'eth3-up', 'sw-up', 'root_cause_failure', 'forecast', 'probability' ])
    del salida
    csvsalida.close()
    logger.info('csv created')

def _update_csv(rx, tx, lost, eth1, eth2, eth3, sw, rcf, forecast, prob):
    csvsalida = open('netstats.csv', 'a', newline='')
    salida = csv.writer(csvsalida)
    datos = [(rx, tx, lost, eth1,  eth2, eth3, sw, rcf, forecast, prob)]
    salida.writerows(datos)
    del salida
    csvsalida.close()
    logger.info('csv updated')

def _create_rcf():
    archivo=open('rcf.txt','w')
    archivo.write('Normal_functioning')
    archivo.close()
    logger.info('rcf created')
def _read_rcf():
    archivo=open('rcf.txt','r')
    linea=archivo.readline()
    archivo.close()
    return linea 


def _read_pipe(stats):
    count = 0
    logger.info('Ready, reading from pipe')
    while True:
        with open('/dev/shm/poxpipe','r') as pipe:
            data = pipe.read()
            p = multiprocessing.Process(target=_read_data, args=(data,stats))
            p.start()
            #count += 1
            #if count % 10 == 0:
                #pass
                #print(stats)
            #time.sleep(1)

def _read_data(data, stats):
#se pasan los valores switch_portstats, switch_down y linkstats al diccionario local stats
    texts = data.split('#')
    for text in texts:
        if len(text) > 0:
            text = json.loads(text)
            if text['type'] == 'switch_portstats':
                #print(text)
                dpid = text['data']['switch']
                # mutate the dictionary
                d = stats[0] 
                # assing values to the dictionary
                d['switches'][dpid]['port_stats'] = text['data']['stats']
                # at this point, changes are not still synced
                # to sync, reassing the dictionary
                stats[0] = d

            #if text['type'] == 'switch_queuestats':
                #print(text)
                #dpid = text['data']['switch']
                #d = stats[0]
                #d['switches'][dpid]['queue_stats'] = text['data']['stats']
                #for puertos in d['switches'][dpid]['queue_stats']:
                #print("Paquetes transmitidos:", puertos['tx_packets'])

            if text['type'] == 'switch_down':
                dpid = text['data']['switch']
                d = stats[0]
                d['switches'][dpid]['switch_down'] = text['data']['down']
                stats[0] = d
           
            if text['type'] == 'linkstats':
               (dpid1, port1),(dpid2, port2) = text['data']['link']
               d = stats[0]
               d['switches'][dpid1]['port_status'] = text['data']
               d['switches'][dpid2]['port_status'] = text['data']
               stats[0] = d
               
def _to_csv():
#se establece un periodo temporal de 14 segundos, y se envían las variables procesadas al módulo bayesiano
    while True:
        try:
                time.sleep(14)
                               
                txpackets = stats[0]['switches'][dpid_p]['port_stats'][2]['tx_packets'] - stats_before[0]['sw_stats']['tx_packets']
                rxpackets = stats[0]['switches'][dpid_p]['port_stats'][0]['rx_packets'] - stats_before[0]['sw_stats']['rx_packets']
                okpackets = stats[0]['switches'][dpid_p2]['port_stats'][1]['rx_packets'] - stats_before[0]['sw_stats']['ok_packets']
                lostpackets = txpackets - okpackets
                print(stats_before[0]['sw_stats']['tx_packets'])
                print(stats_before[1]['sw_stats']['tx_packets'])

                rxlevel = _packets_level(rxpackets)
                txlevel = _packets_level(txpackets)
                lostlevel = _lost_packets_level(lostpackets, txpackets)
                                
                eth1state = _state(1)
                eth2state = _state(2)
                eth3state = _state(3)
                swstate = _sw_state()
                if swstate == False:
                    eth1state = False
                    eth2state = False
                    eth3state = False
                rcf = _read_rcf()
                forecast, prob = _get_forecast(rxlevel, txlevel, lostlevel, eth1state, eth2state, eth3state, swstate)                

                d = stats_before[0]
                d['sw_stats']['tx_packets'] = stats[0]['switches'][dpid_p]['port_stats'][2]['tx_packets']
                d['sw_stats']['rx_packets'] = stats[0]['switches'][dpid_p]['port_stats'][0]['rx_packets']
                d['sw_stats']['ok_packets'] = stats[0]['switches'][dpid_p2]['port_stats'][1]['rx_packets']
                stats_before[0] = d
                
                _update_csv(rxlevel, txlevel, lostlevel, eth1state, eth2state, eth3state, swstate, rcf, forecast, prob)        
        except Exception as e:
                print('Error:',e)
                continue


def _sw_state():
#se obtiene el estado del switch en cuestión
    if 'switch_down' in stats[0]['switches'][dpid_p] and stats[0]['switches'][dpid_p]['switch_down'] == True:
        aux = False
    else:
        aux = True

    return aux
def _state(nport):
#se obtiene el estado del puerto en cuestión
    (dpid1, port1),(dpid2, port2) = stats[0]['switches'][2]['port_status']['link']
    if dpid1 == 2:
        if port1 == nport:
            return stats[0]['switches'][2]['port_status']['up']
        else:
            return True
    else:
        if port2 == nport:
            return stats[0]['switches'][2]['port_status']['up']
        else:
            return True

def _packets_level(packets):
#se establecen los niveles de paquetes según el número recibido por intervalo
    if packets <50:
        aux = "Muy_bajo"
    elif packets < 300:
        aux = "Bajo"
    elif 300 < packets < 600:
        aux = "Normal"
    else:
        aux = "Alto"
    
    return aux

def _lost_packets_level(lostpackets, txpackets):
#se calcula el porcentaje de paquetes perdidos y se establecen los niveles
    if txpackets == 0:
        return "Bajo"
    else:
        percentage = (lostpackets/txpackets)*100
        if percentage < 5:
            aux = "Despreciable"
        elif 5 < percentage < 10:
            aux = "Bajo"
        elif 10 < percentage < 20:
            aux = "Medio"
        else:
            aux = "Alto"

        return aux

def _get_forecast(rxlevel, txlevel, lostlevel, eth1state, eth2state, eth3state, swstate):
#se añaden las evidencias recibidas en el parámetro y se devuelve el valor del nodo root cause failure de más probabilidad
    net.setEvidence("rx_packets_level", rxlevel);
    net.setEvidence("tx_packets_level", txlevel);
    net.setEvidence("lost_packets_level", lostlevel);
    net.setEvidence("eth1_up", eth1state);
    net.setEvidence("eth2_up", eth2state);
    net.setEvidence("eth3_up", eth3state);
    net.setEvidence("sw_up", swstate);
    net.updateBeliefs()

    rcfStatesIds = net.getOutcomeIds("root_cause_failure")
    prob = 0
    for outcomeIndex in range(0, len(rcfStatesIds)):
        if net.getNodeValue("root_cause_failure")[outcomeIndex]>prob:
            prob = net.getNodeValue("root_cause_failure")[outcomeIndex]
            forecast = net.getOutcomeIds("root_cause_failure")[outcomeIndex]
    return forecast, prob

def default_True():
    return 1

def default_zero():
    return 0

def defaultdict_with_zero():
    return defaultdict(default_zero)

def default_list():
    return defaultdict(list)

def port_status(switch, port, stats):
    up = stats[0]['links'].get(switch,{}).get(port,None)
    if up is None:
        return '?'
    if up:
        return 'up'
    return 'down'


if __name__ == '__main__':
    
    logger.info('Starting subprocesses')
    #se inicia la máquina virtual java y se lee el fichero xdsl generado previamente
    jvmPath = jpype.getDefaultJVMPath()
    jvmArg = "-Djava.class.path=/home/mininet/smile.jar"
    startJVM(jvmPath, jvmArg)
    net = JPackage('smile').Network()
    net.readFile("/home/mininet/sdn-diagnosis/monitor/bayesianNetwork.xdsl")
    logger.info("JVM started")

    _create_csv()
    _create_rcf()

    manager = multiprocessing.Manager()
    # create a list proxy and append a mutable object (dict)
    stats = manager.list()
    stats.append({'switches':defaultdict(dict), 'links':defaultdict(dict)})
             
    stats_before = manager.list()
    stats_before.append({'sw_stats':{'tx_packets':0, 'rx_packets':0, 'ok_packets':0, 'eth1':True, 'eth2':True, 'eth3':True, 'state':True}})

    toCsv = multiprocessing.Process(target=_to_csv)
    toCsv.start()

    try:
        _read_pipe(stats)
    except KeyboardInterrupt:
        sys.exit(1)
