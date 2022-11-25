import os
from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from p4utils.utils.sswitch_p4runtime_API import SimpleSwitchP4RuntimeAPI

class RoutingController(object):

    def __init__(self):

        if not os.path.exists('topology.json'):
            print('Could not find topology object!!!\n')
            raise Exception

        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.init()

    def init_ecmp_groups(self):
        self.ecmp_groups = {}
        self.ecmp_group_id = {}
        for sw in self.topo.get_p4switches():
            self.ecmp_groups[sw] = {}
            self.ecmp_group_id[sw] = 1

    def init(self):
        self.connect_to_switches()
        self.reset_states()
        self.set_table_defaults()
        self.init_ecmp_groups()

    def reset_states(self):
        """Resets registers, tables, etc.
        """
        for p4rtswitch, controller in self.controllers.items():
            # Reset grpc server
            controller.reset_state()

            # Connect to thrift server
            thrift_port = self.topo.get_thrift_port(p4rtswitch)
            controller_thrift = SimpleSwitchThriftAPI(thrift_port)
            # Reset forwarding states
            controller_thrift.reset_state()

    def connect_to_switches(self):
        for p4rtswitch, data in self.topo.get_p4switches().items():
            device_id = self.topo.get_p4switch_id(p4rtswitch)
            grpc_port = self.topo.get_grpc_port(p4rtswitch)
            p4rt_path = data['p4rt_path']
            json_path = data['json_path']
            self.controllers[p4rtswitch] = SimpleSwitchP4RuntimeAPI(device_id, grpc_port,
                                                                    p4rt_path=p4rt_path,
                                                                    json_path=json_path)

    def set_table_defaults(self):
        for controller in self.controllers.values():
            controller.table_set_default("ipv4_lpm", "drop", [])
            controller.table_set_default("ecmp_group_to_nhop", "drop", [])

    def add_direct(self, sw):
        """Install an entry for each directly connected host
        """
        for subn in self.topo.get_direct_host_networks_from_switch(sw):
            host_ip = subn.split('.')
            host_ip[3] = '2'
            host_ip = '.'.join(host_ip)
            host_name = self.topo.get_host_name(host_ip)
            intf = self.topo.edge_to_intf[sw][host_name]
            self.controllers[sw].table_add(
                "ipv4_lpm",
                "set_nhop",
                [
                    host_ip + '/32'
                ],
                [
                    intf['addr_neigh'],
                    str(intf['port'])
                ]
            )

    def last_sw_hop(self, sw1, sw2, nh):
        """Install an entry for each single path between switches when the
        destination switch has direct hosts connected
        """
        for subn in self.topo.get_direct_host_networks_from_switch(sw2):
            intf = self.topo.edge_to_intf[sw1][nh]
            self.controllers[sw1].table_add(
                "ipv4_lpm",
                "set_nhop",
                [
                    subn
                ],
                [
                    intf['addr_neigh'],
                    str(intf['port'])
                ]
            )

    def add_ecmp(self, sw1, sw2, paths):
        # ports to use
        ports = []
        path_size = len(paths)
        groups = self.ecmp_groups[sw1]
        for nh in [x[1] for x in paths]:
            intf = self.topo.edge_to_intf[sw1][nh]
            ports.append(str(intf['port']))
        ports.sort()
        index = ",".join(ports)
        if index not in groups:
            self.ecmp_groups[sw1][index] = self.ecmp_group_id[sw1]
            self.ecmp_group_id[sw1] += 1
            for idx, nh in enumerate([x[1] for x in paths]):
                intf = self.topo.edge_to_intf[sw1][nh]
                self.controllers[sw1].table_add(
                    "ecmp_group_to_nhop",
                    "set_nhop",
                    [
                        str(self.ecmp_groups[sw1][index]),
                        str(idx)
                    ],
                    [
                        intf['addr_neigh'],
                        str(intf['port'])
                    ]
                )
        for subn in self.topo.get_direct_host_networks_from_switch(sw2):
            self.controllers[sw1].table_add(
                "ipv4_lpm",
                "ecmp_group",
                [
                    subn
                ],
                [
                    str(self.ecmp_groups[sw1][index]),
                    str(path_size)
                ]
            )

    def route(self):
        for sw1 in self.topo.get_p4switches():
            for sw2 in self.topo.get_p4switches():
                if sw1 == sw2:
                    # source switch and destination switch are the same
                    self.add_direct(sw1)
                elif self.topo.get_direct_host_networks_from_switch(sw2):
                    # destination switch has direct hosts connected
                    min_paths = self.topo.get_shortest_paths_between_nodes(sw1, sw2)
                    print("HERE", sw1, sw2, len(min_paths))
                    if len(min_paths) == 1:
                        # there is a single path between src switch and
                        # destination switch
                        self.last_sw_hop(sw1, sw2, min_paths[0][1])
                    else:
                        # there are multiple paths between src switch and
                        # destination switch
                        self.add_ecmp(sw1, sw2, min_paths)

    def main(self):
        self.route()


if __name__ == "__main__":
    controller = RoutingController().main()
