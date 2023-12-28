import os
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')

def test_directories(host):
    dirs = [
        "/usr/local/etc/kamailio"
    ]
    for dir in dirs:
        d = host.file(dir)
        assert d.is_directory
        assert d.exists

def test_files(host):
    files = [
        "/usr/local/etc/kamailio/dispatcher.list.sql",
        "/usr/local/etc/kamailio/kamailio.cfg",
        "/usr/local/etc/kamailio/kamctlrc",
        "/usr/local/sbin/kamailio",
        "/etc/systemd/system/kamailio.service",
        "/usr/local/bin/rtpproxy",
        "/etc/systemd/system/rtpproxy.service",
    ]
    for file in files:
        f = host.file(file)
        assert f.exists
        assert f.is_file

def test_service(host):
    services = [
      "kamailio",
      "rtpproxy"
    ]

    for service in services:
      s = host.service(service)
      assert s.is_enabled
      assert s.is_running

def test_socket(host):
    sockets = [
        "tcp://127.0.0.1:5080",
        "udp://127.0.0.1:5080"
    ]
    for socket in sockets:
        s = host.socket(socket)
        assert s.is_listening
