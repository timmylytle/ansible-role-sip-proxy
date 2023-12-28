# ansible-role-sip-proxy
This ansible role installs a SIP and RTP proxy to load balance multiple Miarec recorders. This is accomplished using open source sip server [Kamailio](https://github.com/kamailio/kamailio) and [RTPProxy](https://github.com/sippy/rtpproxy)

## Requirements
Kamailio requires a database to maintain call state and routing destinations, this ansible role assumes this will be a remote PostgreSQL instance
- PostgreSQL instance
- Postgresql user with permission to create users and databases

## Architecture and Key Functions
Kamailio and RTPProxy will act as a SIP and RTP Proxy between Voice Platforms and MiaRec Recorders

```
      Internet           \        Private Subnet (NAT'd)         \        Private Subnet
                         \                                       \                   +-----------------+
                         \                                       \     +------------>| MiaRec Recorder |
                         \                                       \     |  SIP/RTP    +-----------------+
                         \                 +----------------+    \     |
                    +---------+  SIP/RTP   |                |----\-----+
 {   Voice  }-------| NAT GW  |----------->|  Kamailio /    |    \     |             +-----------------+
 { Platform }       +---------+            |    RTPProxy    |    \     +------------>| MiaRec Recorder |
                         \                 |                |    \        SIP/RTP    +-----------------+
                         \                 +----------------+    \
                         \                               |       \                      +--------------+
                         \                               +-------\--------------------->|  PostgreSQL  |
                         \                                       \                      +--------------+
```
### NAT
The SIP/RTP Proxy is installed in a private network that is behind a NAT Gateway, a public ipv4 address is NAT'd to SIP-Proxy private address, Kamailio handle NAT translation of SIP headers and SDP via [`nathelper module`](https://kamailio.org/docs/modules/5.0.x/modules/nathelper.html) and [`rtpproxy module`](https://kamailio.org/docs/modules/5.1.x/modules/rtpproxy.html)    SDP rewrite depends on RTPProxy application to

`nathelper` and `rtpproxy` module config is defined in '/usr/local/src/kamailio-5.5/kamailio/kamilio.cfg'
```
...
listen=udp:10.0.0.10:5060 advertise 1.2.3.4:5060
listen=tcp:10.0.0.10:5060 advertise 1.2.3.4:5060
...
loadmodule "nathelper.so"
loadmodule "rtpproxy.so"
...
modparam("rtpproxy", "rtpproxy_sock", "udp:127.0.0.1:7722")
modparam("nathelper", "natping_interval", 30)
modparam("nathelper", "ping_nated_only", 1)
modparam("nathelper", "sipping_bflag", FLB_NATSIPPING)
modparam("nathelper", "sipping_from", "sip:pinger@kamailio.org")
modparam("nathelper|registrar", "received_avp", "$avp(RECEIVED)")
```

RTPProxy config is defined in '/etc/systemd/system/rtpproxy.service'
```
[Service]
...
Environment='OPTIONS= -f -A 1.2.3.4 -F -l 10.0.0.10 -m 20000 -M 30000 -s udp:*:7722 -d INFO'
```

### LoadBalancing
Calls are loadbalanceed between Recorder instances using the [`dispatcher module`](https://kamailio.org/docs/modules/4.3.x/modules/dispatcher.html).

Loadbalancing is affected by several variables, listed [below](./README.md#loadbalancing-1). By default, calls are distributed equally to all recorders round-robin style

`dispatcher` module config is defined in '/usr/local/src/kamailio-5.5/kamailio/kamilio.cfg' and in the `dispatcher table` in the postgreSQL database

'kamilio.cfg'
```
loadmodule "dispatcher.so"
...
modparam("dispatcher", "db_url", DBURL)
modparam("dispatcher", "ds_ping_interval", 10)
modparam("dispatcher", "ds_ping_method", "OPTIONS")
modparam("dispatcher", "ds_probing_threshold", 10)
modparam("dispatcher", "ds_inactive_threshold", 10)
modparam("dispatcher", "ds_ping_latency_stats", 1)
modparam("dispatcher", "ds_probing_mode", 1)
...

request_route {
...
        # LOADBALANCE processing
        if(method=="INVITE"){
              ds_select_dst(1, 4);
              record_route();
              route(RELAY);
        }
...
}

```
Example output of  kamailio/dispatcher
```
kamailio=> SELECT * FROM dispatcher;
 id | setid |           destination            | flags | priority | attrs |        description
----+-------+----------------------------------+-------+----------+-------+---------------------------
  1 |     1 | sip:10.0.0.10:5080;transport=tcp |     0 |        0 |       | recorder0
  2 |     1 | sip:10.0.0.11:5080;transport=tcp |     0 |        0 |       | recorder1
(2 rows)
```
## Role Varialbles

### Required Variables

`Host Variables` These varaibles are unique per host, as such they should be supplied as hostvars in the ansible inventory
- `public_ip_address` public ipv4 address of host
- `private_ip_address` private ipv4 address of host

`Group Variables` These varaibles apply to the entire deployment, as such they can be assigned to group vars
- `dbhost` URL or IP address of postgres instance
- `dbuser_root` root user with privledge to create user and databases
- `dbpass_root` password for `dbuser_root`

Example Ansible Inventory
```ini
[all]
sipproxy0 public_ip_address=1.2.3.4 private_ip_address=10.0.0.1
sipproxy1 public_ip_address=5.6.7.8 private_ip_address=10.0.0.2

[sipproxy:vars]
dbhost = database.example.com
dbuser_root = rootuser
dbpass_root = secert
```

### Optional Variables
- `kamailio_version` version of kamailio to installed, default = 5.5, Kamailio Branches listed [here](https://github.com/kamailio/kamailio/branches)

#### Database
- `db_root` name of root database, used for inital creation of kamailio databse default = 'miarecdb'
- `dbport` tcp port where postgresQL instance is listening, default = 5432
- `db_kam` name of database that will be created, default = 'kamailio'
- `dbuser_kam` username that kamailio modules will with to access PostgreSQL database, default = 'kamailio'
- `dbpass_kam` password for `dbuser_kam`

#### Connectivty
- `sip_tcp_port` tcp port that will be used for SIP signaling, default = '5080'
- `sip_udp_port` udp port that will be used for SIP signaling, default = '5080'
- `rtp_start` starting UDP port for RTP range, default = 20000
- `rtp_stop` ending UDP port for RTP range, default = 30000
- `tcp_max_connections` Maximum number of tcp connections (if the number is exceeded no new tcp connections will be accepted) this includes TLS connection, default = 2048
- `tcp_connection_lifetime` Lifetime in seconds for TCP sessions. TCP sessions which are inactive for longer than tcp_connection_lifetime will be closed by Kamailio, default = 3605
- `enable_NAT_keepalive` It might be required for SIP OPTIONS messages to go through NAT depending on archetecture, if so this will need to be enabled to accuratly rewrite OPTION messages, default = false

#### Loadbalancing
- `disp_set` dispatcher set - a partition name followed by colon and an id of the set or a list of sets from where to pick up destination address
- `disp_alg` disaptcher alg - the algorithm(s) used to select the destination address (variables are accepted)

#### Recorder hostvars for loadbalancing

The following varaibles apply to individual recorder hosts and effect how the sip proxy will interact with them, [additional documenation here](https://kamailio.org/docs/modules/4.3.x/modules/dispatcher.html#idp51005116)

- `siprec_port` port recorder will be listening on, default = '5080'
- `siprec_protocol` tcp or udp, default = 'tcp'
- `siprec_flags` Various flags that affect dispatcher's behaviour, default = '0'
- `siprec_priority` sets the priority in destination list (based on it is done the initial ordering inside the set), default = '0'
- `siprec_attrs` extra fields in form of name1=value1;...;nameN=valueN., default = ' '

Example
```ini
[all]
rec0.example siprec_port=5060 siprec_protocol=udp siprec_attrs='weight=60' private_ip_address=10.0.0.10
rec1.example siprec_attrs="weight=40" private_ip_address=10.0.0.11
```
result:
- rec0 would recieve siprec on udp:5060 and recieve 60% of calls
- rec1 would recieve siprec on tcp:5080 and recieve 40% of calls

#### Debug
- `enable_debug` enables the debugger module, default= 'false'
- `debug_level` LOG Levels: 3=DBG, 2=INFO, 1=NOTICE, 0=WARN, -1=ERR, default = 2
- `log_stderror` set to 'yes' to print log messages to terminal, otherwise, debug will be available in syslog, default ='no'
- `enable_jsonrpc` enables [Kamailio RPC Interface](https://www.kamailio.org/w/2020/11/kamailio-jsonrpc-client-with-http-rest-interface/), default = false

#### TLS (This feature is not tested)
- `enable_tls` Enables TLS module, default = false
- `tls_max_connections` Maxium number of tls connection, must not exceed `tcp_max_connections`, default = 2048

#### Antiflood
- `enable_anitflood` Enables [Anitflood](https://www.kamailio.org/docs/modules/devel/modules/pike.html) feature, which automatically bans IP addresses with excessive messaging, default = 'true'
- `pike_sample_time` Time period in seconds used for sampling (or the sampling accuracy). The smaller the better, but slower, default = '2'
- `pike_reqs_density` How many requests should be allowed per `sampling_time_unit` before blocking all the incoming request from that source, default = '30'
- `pike_remove_latency` Specifies for how long the IP address will be kept in memory after the last request from that IP address. It's a sort of timeout value, in seconds, default = '120'
- `ipban_expire` Time in seconds ip will be stored in ipban table, default = '300'

## Example Role Usage
Example Playbook
```yaml
- name: Deploy Kamailio and rtpproxy
  hosts:
    - sipproxy
  become: true
  pre_tasks:
    - set_fact:
        tmp_dest:
          name: "{{ hostvars[item].inventory_hostname }}"
          ip: "{{ hostvars[item].private_ip_address }}"
          port: "{{ hostvars[item].siprec_port | default('5080') }}"
          protocol: "{{ hostvars[item].siprec_protocol | default('tcp') }}"
          flags: "{{ hostvars[item].siprec_flags | default('0') }}"
          priority: "{{ hostvars[item].siprec_priority | default('0') }}"
          attrs: "{{ hostvars[item].siprec_attrs | default('') }}"
      with_items: "{{ groups.recorder }}"
      register: _tmp_dispatch_dest
    - set_fact:
        dispatcher_destinations: "{{ _tmp_dispatch_dest.results | selectattr('ansible_facts', 'defined') | map(attribute='ansible_facts.tmp_dest') | list }}"
  roles:
    - role: 'ansible-role-sip-proxy'
  tags: 'sipproxy'
```

Example Inventory
```ini
[all]
sipproxy0 ansible_host=10.0.0.1 public_ip_address=1.2.3.4 private_ip_address=10.0.0.1
sipproxy1 ansible_host=10.0.0.2 public_ip_address=5.6.7.8 private_ip_address=10.0.0.2
recorder0 ansible_host=10.0.0.3 private_ip_address=10.0.0.3 siprec_port=5060 siprec_protocol=udp siprec_attrs='weight=75'
recorder1 ansible_host=10.0.0.4 private_ip_address=10.0.0.4 siprec_attrs='weight=25'

[recorder]
recorder0
recorder1

[sipproxy]
sipproxy0
sipproxy1

[sipproxy:vars]
dbhost = database.example.com
dbrootpass = secert
enable_debug = true
debug_level = 3
```

## Useful Commands
`kamctl dispatcher show` - will show what is in the dispatcher table in kamailio database
output:
```-e dispatcher gateways
1|1|sip:10.0.0.3:5060;transport=udp|0|0|weight=75|recorder0
2|1|sip:10.0.0.4:5080;transport=tcp|0|0|weight=25|recorder1
```

`kamcmd dispatcher.reload` - this will restart the dispatcher module, this is required anytime changes are made to the disaptcher table

`kamcmd dispatcher.list` - will show the current state of the dispatcher destinations
output:
FLAGS = Current Status
 - `AP – Active Probing` – Destination is responding to pings & is up
 - `IP – Inactive Probing` – Destination is not responding to pings and is probably unreachable
 - `DX – Destination is disabled` (administratively down)
 - `AX` – Looks like is up or is coming up, but has yet to satisfy minimum thresholds to be considered up (ds_inactive_threshold)
 - `TX` – Looks like or is, down. Has stopped responding to pings but has not yet satisfied down state failed ping count (ds_probing_threshold)
```
{
        NRSETS: 1
        RECORDS: {
                SET: {
                        ID: 1
                        TARGETS: {
                                DEST: {
                                        URI: sip:10.0.0.3:5060;transport=udp
                                        FLAGS: AP
                                        PRIORITY: 0
                                        LATENCY: {
                                                AVG: 0.000000
                                                STD: 0.000000
                                                EST: 0.000000
                                                MAX: 0
                                                TIMEOUT: 54
                                        }
                                }
                                DEST: {
                                        URI: sip:10.0.0.4:5080;transport=tcp
                                        FLAGS: AP
                                        PRIORITY: 0
                                        LATENCY: {
                                                AVG: 0.000000
                                                STD: 0.000000
                                                EST: 0.000000
                                                MAX: 0
                                                TIMEOUT: 115
                                        }
                                }
                        }
                }
        }
}
```

`kamcmd dispatcher.set_state [state] [destination]`  This will manually set the state of a destination

example to admin down a target
```
kamcmd dispatcher.set_state dx 1 sip:10.0.0.3:5080;transport=tcp
```