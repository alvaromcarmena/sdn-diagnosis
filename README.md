# sdn-diagnosis
Fault Diagnosis on SDN Networks

## Mininet
Launch mininet:
```
sudo mn --mac --custom sdn-monitor/mininet/topo.py --topo minivideostreaming --switch ovsk --controller remote
```

Lauch with monitor module enabled and grepping for interesting data only:
```
sudo ./pox.py forwarding.l2_pairs openflow.discovery openflow.spanning_tree --no-flood --hold-down monitor log.level --DEBUG 2>&1 | grep -i "Monitor\|connected\|ports"
```

Aditionally, another combination of pox modules:
```
./pox.py openflow.discovery proto.arp_responder  l3_rules --rules_path=<rules-path> stats_monitor log.level --INFO 2>&1 | grep -i "Monitor\|connected\|ports\|rule\|discovery\|arp"
```

## Video streaming
To launch a server to stream video via HTTP (this can depend on the video source):
```
vlc <video-source> :sout='#transcode{vcodec=h264,scale=Auto,acodec=mpga,ab=128,channels=2,samplerate=44100}:http{mux=ffmpeg{mux=flv},dst=:8080/test}' :sout-keep
```

To launch a client that listens to this streaming:
```
vlc http://<server-ip>:8080/test
```

## Net errors emulation
To emulate an error on a link using tc:
```
 <switch> tc qdisc change dev <switch>-<interface> parent 5:1 handle 10: netem <options>
```
To emulate lost packets using tc
```
 <switch> tc qdisc change dev <switch>-<interface> parent 5:1 handle 10: netem loss <percentage>
```
To emulate a port up/down in switch with sh command
```
 sh ifconfig <switch>-<interface> up/down
```
To emulate a switch start/stop
```
 switch <switch> start/stop
```

