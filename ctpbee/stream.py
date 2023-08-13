"""
交易流实现
订单协议


"""
import json
from threading import Thread

from ctpbee.constant import TickData, OrderData, OrderRequest, CancelRequest, ContractData

from ctpbee.level import CtpbeeApi
from ctpbee.jsond import dumps, loads

from redis import Redis
from json import loads as ld


class UDDR:
    """
    上行消息 订单数据
    """

    def __init__(self, msg):
        self.index = 0
        self.obj = None
        try:
            self.__parse__(msg)
        except Exception:
            pass

    def __parse__(self, msg):
        msg = ld(msg)
        self.index = msg["index"]
        self.obj = loads(msg["order_req"])


class DDDR:
    """
    下行消息
    """

    def __init__(self, obj, index=None):
        self.order = dumps(obj)
        self.index = index

    def encode(self) -> str:
        """
        """
        return json.dumps(dict(
            data=self.order,
            index=self.index
        ))


class Dispatcher(CtpbeeApi):

    def __init__(self, name, app=None):
        super().__init__(name, app=app)
        tcp_addr = self.app.config.get("RD_CLIENT_ADDR", "127.0.0.1")
        tcp_port = self.app.config.get("RD_CLIENT_PORT", 6379)
        db = self.app.config.get("RD_CLIENT_DB", 0)
        self.order_up_kernel = self.app.config.get("ORDER_UP_KERNEL", "ctpbee_order_up_kernel")
        self.tick_kernel = self.app.config.get("TICK_KERNEL", "ctpbee_tick_kernel")
        self.order_down_kernel = self.app.config.get("ORDER_DOWN_KERNEL", "ctpbee_order_down_kernel")
        self.rd_client = Redis(host=tcp_addr, port=tcp_port, db=db, decode_responses=True)
        self.order_key_map = dict()
        threader = Thread(target=self.listen, daemon=True)
        threader.start()
        self.init = False

    def listen(self):
        """
        监听来自订单通道的消息
        """
        pub = self.rd_client.pubsub()
        pub.subscribe(self.order_up_kernel)
        for item in pub.listen():
            uddr = UDDR(item)
            if uddr.obj is None:
                pass
            elif type(uddr.obj) == OrderRequest:
                order_id = self.action.send_order(order=uddr.obj)
                self.order_key_map[order_id] = uddr.index

            elif type(uddr.obj) == CancelRequest:
                self.action.cancel_order(uddr.obj)
                self.order_key_map[uddr.obj.order_id] = uddr.index
            else:
                pass

    def on_order(self, order: OrderData) -> None:
        index = self.order_key_map.get(order, 0)
        order_message = DDDR(obj=order, index=index)
        self.rd_client.publish(self.order_down_kernel, order_message.encode())

    def on_tick(self, tick: TickData) -> None:
        print(tick)
        tick_message = DDDR(obj=tick, index=None)
        self.rd_client.publish(self.tick_kernel, tick_message.encode())

    def on_contract(self, contract: ContractData) -> None:
        if not self.init:
            for i in self.app.config.get("SUBSCRIBE_CONTRACT", []):
                self.action.subscribe(i)
            self.info("行情订阅成功")
            self.init = True
