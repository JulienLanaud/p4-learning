from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_p4runtime_API import SimpleSwitchP4RuntimeAPI


topo = load_topo('topology.json')
controllers = {}
sw_name = 's1'

for switch, data in topo.get_p4rtswitches().items():
    controllers[switch] = SimpleSwitchP4RuntimeAPI(data['device_id'], data['grpc_port'],
                                                   p4rt_path=data['p4rt_path'],
                                                   json_path=data['json_path'])

controller = controllers[sw_name]

# TODO: populate table my_table
controller.table_clear('my_table')

controller.table_add("my_table", "my_action", ['00:00:0a:00:00:01'], ['1'])
controller.table_add("my_table", "my_action", ['00:00:0a:00:00:02'], ['2'])
controller.table_add("my_table", "my_action", ['00:00:0a:00:00:03'], ['3'])
controller.table_add("my_table", "my_action", ['00:00:0a:00:00:04'], ['4'])

# Get port list
interfaces_to_port = topo.get_node_intfs(fields=['port'])[sw_name].copy()
# Filter lo and cpu port
interfaces_to_port.pop('lo', None)
interfaces_to_port.pop(topo.get_cpu_port_intf(sw_name), None)
port_list = list(interfaces_to_port.values())

# TODO: add broadcast group
controller.mc_mgrp_create(1, port_list)
