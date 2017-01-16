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

dpid1 = "00-00-00-00-00-01"
dpid2 = "00-00-00-00-00-02"
dpid3 = "00-00-00-00-00-03"
dpid4 = "00-00-00-00-00-04"
dpid5 = "00-00-00-00-00-05"
dpid6 = "00-00-00-00-00-06"
dpid7 = "00-00-00-00-00-07"
dpid8 = "00-00-00-00-00-08"

networkSwitches = [dpid1, dpid2, dpid3, dpid4, dpid5, dpid6, dpid7, dpid8]

def _create_csv():
    csvsalida = open('netstats.csv', 'w', newline='')
    salida = csv.writer(csvsalida)
    salida.writerow(['rx_packets_level', 'tx_packets_level', 'lost_packets_level', 'auxPort-up', 'outPort-up', 'inPort-up', 'sw-up', 'root_cause_failure', 'forecast', 'prob'])
    del salida
    csvsalida.close()
    logger.info('csv created')

def _update_csv(rx, tx, lost, auxPort, outPort, inPort, sw, rcf, forecast, prob):
    csvsalida = open('netstats.csv', 'a', newline='')
    salida = csv.writer(csvsalida)
    datos = [(rx, tx, lost, auxPort,  outPort, inPort, sw, rcf, forecast, prob)]
    print(datos)
    salida.writerows(datos)
    del salida
    csvsalida.close()
    logger.info('csv updated')

def _create_rcf():
    archivo=open('rcf.txt','w')
    archivo.write('all_switches,Normal_functioning,,')
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
               (dpid_1, port_1),(dpid_2, port_2) = text['data']['link']
               d = stats[0]
               d['switches'][dpid_1]['port_status'] = text['data']
               d['switches'][dpid_2]['port_status'] = text['data']
               stats[0] = d
               
def _to_csv():
##se establece un periodo temporal de 14 segundos, y se envían las variables procesadas al módulo bayesiano
    while True:
        try:
                time.sleep(14)
                
                rcf = _read_rcf()
                #se lee el fallo producido
                arrayRcf = rcf.split(",")
                #se cogen las variables de todos los switches y se actualiza el csv 8 veces, 1 por switch
                for dpid in networkSwitches:
                   txLevel, rxLevel, lostLevel, auxPortState, outPortState, inPortState, swState = _get_variables(dpid)       
                  
                   if(arrayRcf[0]=='all_switches'):
                       rootCause = arrayRcf[0+1]
                   elif(arrayRcf[0]==dpid):
                       rootCause = arrayRcf[0+1]
                   elif(arrayRcf[2]==dpid):
                       rootCause = arrayRcf[2+1]
                   else:
                       rootCause = 'Normal_functioning'
                   forecast, prob = _get_forecast(rxLevel, txLevel, lostLevel, auxPortState, outPortState, inPortState, swState)
                   
                   _update_csv(rxLevel, txLevel, lostLevel, auxPortState, outPortState, inPortState, swState, rootCause, forecast, prob)
                
        except Exception as e:
                print('Error:',e)
                continue

def _get_variables(dpid):
#se procesan las distintas variables haciéndolas discretas y se devuelven 
   switchType = rules[0][dpid]['switch_type']
   if switchType == 'server_switch':
       txPackets, rxPackets, lostPackets = _calculate_packets_serverSwitch(dpid)
   elif switchType == 'main_ring':
       txPackets, rxPackets, lostPackets = _calculate_packets_mainRing(dpid)
   elif switchType == 'host_switch':
       txPackets, rxPackets, lostPackets = _calculate_packets_hostSwitch(dpid)
   txLevel = _packets_level(txPackets)
   rxLevel = _packets_level(rxPackets)
   lostLevel = _lost_packets_level(lostPackets, txPackets)

   auxPort = rules[0][dpid]['aux_port']['number']
   outPort = rules[0][dpid]['out_port']['number']
   inPort = rules[0][dpid]['in_port']['number']
   #se calcula su estado
   auxPortState = _state(dpid, auxPort)
   outPortState = _state(dpid, outPort)
   inPortState = _state(dpid, inPort)
   swState = _sw_state(dpid)
   if swState == False:
       auxPortState = False
       outPortState = False
       inPortState = False    
   return txLevel, rxLevel, lostLevel, auxPortState, outPortState, inPortState, swState    

def _calculate_packets_serverSwitch(dpid):
   #cogemos la posición que tiene cada puerto en el array de portStats
   inPort = rules[0][dpid]['in_port']['position']  
   outPort = rules[0][dpid]['out_port']['position']
   auxPort = rules[0][dpid]['aux_port']['position']
   #auxPort = rules[0][dpid]['aux_port']['position']
   dpid_nextSwitch = rules[0][dpid]['next_switch']
   inPort_nextSwitch = rules[0][dpid_nextSwitch]['in_port']['position']
   dpid_auxSwitch = rules[0][dpid]['aux_switch']
   inPort_auxSwitch = rules[0][dpid_auxSwitch]['in_port']['position']

   txpackets = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] + stats[0]['switches'][dpid]['port_stats'][auxPort]['tx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['tx_packets']
   rxpackets = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['rx_packets']
   okpackets = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets'] + stats[0]['switches'][dpid_auxSwitch]['port_stats'][inPort_auxSwitch]['rx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['ok_packets']
   lostpackets = txpackets - okpackets
   #print(dpid, "Tx packets:", txpackets, "Rx packets:", rxpackets,"OK packets:", okpackets, "Lost packets:", lostpackets)   

   #se actualizan los valores de txpackets, rxpackets y okpackets, ya que pox acumula únicamente los totales
   d = stats_before[associations[0][dpid]]
   d['sw_stats']['tx_packets'] = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] + stats[0]['switches'][dpid]['port_stats'][auxPort]['tx_packets']
   d['sw_stats']['rx_packets'] = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets']
   d['sw_stats']['ok_packets'] = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets'] + stats[0]['switches'][dpid_auxSwitch]['port_stats'][inPort_auxSwitch]['rx_packets']
   stats_before[associations[0][dpid]] = d
   
   #se considera que en los switches de cliente(s3, s4 y s5) no se pueden perder paquetes, ya que pox no permite recoger datos de los host
   if dpid == (dpid3 or dpid4 or dpid5):
      lostpackets = 0

   return txpackets, rxpackets, lostpackets

def _calculate_packets_mainRing(dpid):
   #cogemos la posición que tiene cada puerto en el array de portStats
   inPort = rules[0][dpid]['in_port']['position']
   outPort = rules[0][dpid]['out_port']['position']
   #auxPort = rules[0][dpid]['aux_port']['position']
   dpid_nextSwitch = rules[0][dpid]['next_switch']
   inPort_nextSwitch = rules[0][dpid_nextSwitch]['in_port']['position']

   txpackets = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['tx_packets']
   rxpackets = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['rx_packets']
   okpackets = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['ok_packets']
   lostpackets = txpackets - okpackets
   #print(dpid, "Tx packets:", txpackets, "Rx packets:", rxpackets,"OK packets:", okpackets, "Lost packets:", lostpackets)

   #se actualizan los valores de txpackets, rxpackets y okpackets, ya que pox acumula únicamente los totales
   d = stats_before[associations[0][dpid]]
   d['sw_stats']['tx_packets'] = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets']
   d['sw_stats']['rx_packets'] = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets']
   d['sw_stats']['ok_packets'] = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets']
   stats_before[associations[0][dpid]] = d

   #se considera que en los switches de cliente(s3, s4 y s5) no se pueden perder paquetes, ya que pox no permite recoger datos de los host
   if dpid == (dpid3 or dpid4 or dpid5):
      lostpackets = 0

   return txpackets, rxpackets, lostpackets

def _calculate_packets_hostSwitch(dpid):
   #cogemos la posición que tiene cada puerto en el array de portStats
   inPort = rules[0][dpid]['in_port']['position']
   outPort = rules[0][dpid]['out_port']['position']
   auxPort = rules[0][dpid]['aux_port']['position']
   #dpid_nextSwitch = rules[0][dpid]['next_switch']
   #inPort_nextSwitch = rules[0][dpid_nextSwitch]['in_port']['position']

   txpackets = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] + stats[0]['switches'][dpid]['port_stats'][auxPort]['tx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['tx_packets']
   rxpackets = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['rx_packets']
   #okpackets = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets'] + stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] - stats_before[associations[0][dpid]]['sw_stats']['ok_packets']
   #lostpackets = txpackets - okpackets
   okpackets = txpackets
   lostpackets = txpackets - okpackets
   lostpackets = 0
   #print(dpid, "Tx packets:", txpackets, "Rx packets:", rxpackets,"OK packets:", okpackets, "Lost packets:", lostpackets)

   #se actualizan los valores de txpackets, rxpackets y okpackets, ya que pox acumula únicamente los totales
   d = stats_before[associations[0][dpid]]
   d['sw_stats']['tx_packets'] = stats[0]['switches'][dpid]['port_stats'][outPort]['tx_packets'] + stats[0]['switches'][dpid]['port_stats'][auxPort]['tx_packets'] 
   d['sw_stats']['rx_packets'] = stats[0]['switches'][dpid]['port_stats'][inPort]['rx_packets']
   #d['sw_stats']['ok_packets'] = stats[0]['switches'][dpid_nextSwitch]['port_stats'][inPort_nextSwitch]['rx_packets']
   stats_before[associations[0][dpid]] = d

   #se considera que en los switches de cliente(s3, s4 y s5) no se pueden perder paquetes, ya que pox no permite$
   if dpid == (dpid3 or dpid4 or dpid5):
      lostpackets = 0

   return txpackets, rxpackets, lostpackets
def _sw_state(dpid):
    if 'switch_down' in stats[0]['switches'][dpid] and stats[0]['switches'][dpid]['switch_down'] == True:
        aux = False
    else:
        aux = True

    return aux
def _state(dpid, nport):
    #se obtiene el número de switch asociado al dpid
    switchNumber =  associations[0][dpid]
    (dpid_1, port_1),(dpid_2, port_2) = stats[0]['switches'][switchNumber]['port_status']['link']
    if dpid_1 == switchNumber:
        if port_1 == nport:
            return stats[0]['switches'][switchNumber]['port_status']['up']
        else:
            return True
    else:
        if port_2 == nport:
            return stats[0]['switches'][switchNumber]['port_status']['up']
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

def _get_forecast(rxlevel, txlevel, lostlevel, auxPortState, outPortState, inPortState, swstate):
#se añaden las evidencias recibidas en el parámetro y se devuelve el valor del nodo root cause failure de más probabilidad
    net.setEvidence("rx_packets_level", rxlevel);
    net.setEvidence("tx_packets_level", txlevel);
    net.setEvidence("lost_packets_level", lostlevel);
    net.setEvidence("eth1_up", auxPortState);
    net.setEvidence("eth2_up", outPortState);
    net.setEvidence("eth3_up", inPortState);
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

    associations = manager.list()
    associations.append({dpid1:1, dpid2:2, dpid3:3, dpid4:4, dpid5:5, dpid6:6, dpid7:7, dpid8:8})

    rules = manager.list()
    #Para cada switch se asocia el puerto de entrada al número correspondiente de puerto y a la posición en la que lo guarda pox, pox guarda la eth3 en la posición 0 del array.
    rules.append({dpid1:{'in_port':{'position': 0, 'number':3}, 
                         'out_port':{'position': 2, 'number':2},
                         'aux_port':{'position': 1, 'number':1}, 
                         'next_switch':dpid5,
                         'switch_type': 'main_ring'}, 
                  dpid2:{'in_port':{'position': 0, 'number':3},
                         'out_port':{'position': 2, 'number':2}, 
                         'aux_port':{'position': 1, 'number':1},
                         'next_switch':dpid3,
                         'switch_type': 'main_ring'}, 
                  dpid3:{'in_port':{'position': 1, 'number':1},
                         'out_port':{'position': 0, 'number':3}, 
                         'aux_port':{'position': 2, 'number':2},
                         'next_switch':dpid3,
                         'switch_type': 'host_switch'}, 
                  dpid4:{'in_port':{'position': 2, 'number':2},
                         'out_port':{'position': 0, 'number':3},
                         'aux_port':{'position': 1, 'number':1}, 
                         'next_switch':dpid4,
                         'switch_type': 'host_switch'}, 
                  dpid5:{'in_port':{'position': 2, 'number':2}, 
                         'out_port':{'position': 0, 'number':3},
                         'aux_port':{'position': 1, 'number':1},
                         'next_switch':dpid4,
                         'switch_type': 'host_switch'}, 
                  dpid6:{'in_port':{'position': 0, 'number':3}, 
                         'out_port':{'position': 1, 'number':1},
                         'aux_port':{'position': 2, 'number':2},
                         'next_switch':dpid1,
                         'switch_type': 'main_ring'},
                  dpid7:{'in_port':{'position': 0, 'number':3}, 
                         'out_port':{'position': 1, 'number':1},
                         'aux_port':{'position': 2, 'number':2},
                         'next_switch':dpid2,
                         'switch_type': 'main_ring'},
                  dpid8:{'in_port':{'position': 0, 'number':3},
                         'out_port':{'position': 1, 'number':1},
                         'aux_port':{'position': 3, 'number':2},
                         'next_switch':dpid6,
                         'aux_switch':dpid7,
                         'switch_type': 'server_switch'}})

    stats_before = manager.list()
    
    x = 0
    while x <= 8:
        stats_before.append({'sw_stats':{'tx_packets':0, 'rx_packets':0, 'ok_packets':0}})
        x = x + 1
    toCsv = multiprocessing.Process(target=_to_csv)
    toCsv.start()

    try:
        _read_pipe(stats)
    except KeyboardInterrupt:
        sys.exit(1)
