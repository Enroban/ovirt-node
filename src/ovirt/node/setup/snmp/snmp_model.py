#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# cim.py - Copyright (C) 2013 Red Hat, Inc.
# Written by Fabian Deutsch <fabiand@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.  A copy of the GNU General Public License is
# also available at http://www.gnu.org/copyleft/gpl.html.
from ovirt.node import utils
from ovirt.node.config.defaults import NodeConfigFileSection
from ovirt.node.utils import process, system, fs
import os.path


snmp_conf = "/var/lib/net-snmp/snmpd.conf"


def enable_snmpd(password):
    system.service("snmpd", "stop")

    # get old password #
    if os.path.exists("/tmp/snmpd.conf"):
        conf = "/tmp/snmpd.conf"
    else:
        conf = snmp_conf
    cmd = "cat %s|grep createUser| grep -v '^#' | awk '{print $4}'" % conf
    oldpwd = process.pipe(cmd, shell=True).strip()
    process.call("sed -c -ie '/^createUser root/d' %s" % snmp_conf, shell=True)
    f = open(snmp_conf, "a")
    # create user account
    f.write("createUser root SHA %s AES\n" % password)
    f.close()

    # change existing password
    if len(oldpwd) > 0:
        system.service("snmpd", "start")
        pwd_change_cmd = (("snmpusm -v 3 -u root -n \"\" -l authNoPriv -a " +
                           "SHA -A %s localhost passwd %s %s -x AES") %
                          (oldpwd, oldpwd, password))
        process.check_call(pwd_change_cmd, shell=True)
        # Only reached when no excepion occurs
        process.call(["rm", "-rf", "/tmp/snmpd.conf"])
        system.service("snmpd", "stop")
    fs.Config().persist(snmp_conf)

    if not any([x for x in open('/etc/snmp/snmpd.conf').readlines()
                if 'rwuser root' in x]):
        with open('/etc/snmp/snmpd.conf', 'a') as f:
            f.write("rwuser root")
    fs.Config().persist("/etc/snmp/snmpd.conf")

    system.service("snmpd", "start")


def disable_snmpd():
    system.service("snmpd", "stop")
    # copy to /tmp for enable/disable toggles w/o reboot
    process.check_call(["cp", "/etc/snmp/snmpd.conf", "/tmp"])
    process.check_call("sed -c -ie '/^createUser root/d' %s" % snmp_conf,
                       shell=True)
    fs.Config().unpersist(snmp_conf)


class SNMP(NodeConfigFileSection):
    """Configure SNMP

    >>> from ovirt.node.utils import fs
    >>> n = SNMP(fs.FakeFs.File("dst"))
    >>> n.update(True)  # doctest: +ELLIPSIS
    <ovirt.node.setup.snmp.snmp_model.SNMP object at ...>
    >>> n.retrieve()
    {'enabled': True}
    """
    keys = ("OVIRT_SNMP_ENABLED",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, enabled):
        return {"OVIRT_SNMP_ENABLED":
                "1" if utils.parse_bool(enabled) else None}

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"enabled":
                    True if cfg["enabled"] == "1" else None})
        return cfg

    def transaction(self, snmp_password):
        cfg = self.retrieve()
        enabled = cfg["enabled"]

        tx = utils.Transaction("Configuring SNMP")

        class ConfigureSNMP(utils.Transaction.Element):
            state = ("Enabling" if enabled else "Disabling")
            title = "%s SNMP and setting the password" % state

            def commit(self):
                if enabled and snmp_password:
                    enable_snmpd(snmp_password)
                else:
                    disable_snmpd()

        tx.append(ConfigureSNMP())
        return tx
