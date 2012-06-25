# Implements asyncore-based generic DGRAM transport
import socket, errno, sys
from pysnmp.carrier.asynsock.base import AbstractSocketTransport
from pysnmp.carrier.address import TransportAddressPair
from pysnmp.carrier import error
from pysnmp import debug

sockErrors = { # Ignore these socket errors
    errno.ESHUTDOWN: 1,
    errno.ENOTCONN: 1,
    errno.ECONNRESET: 0,
    errno.ECONNREFUSED: 0,
    errno.EAGAIN: 0,
    errno.EWOULDBLOCK: 0
    }
try:
    # bad FD may happen upon FD closure on n-1 select() event
    sockErrors[errno.EBADFD] = 1
except AttributeError:
    # Windows sockets do not have EBADFD
    pass

class DgramSocketTransport(AbstractSocketTransport):
    sockType = socket.SOCK_DGRAM
    retryCount = 3; retryInterval = 1
    def __init__(self, sock=None, sockMap=None):
        self.__outQueue = []
        AbstractSocketTransport.__init__(self, sock, sockMap)
        
    def openClientMode(self, iface=None):
        if iface is not None:
            try:
                self.socket.bind(iface)
            except socket.error:
                raise error.CarrierError('bind() failed: %s' % (sys.exc_info()[1],))
        return self
    
    def openServerMode(self, iface):
        try:
            self.socket.bind(iface)
        except socket.error:
            raise error.CarrierError('bind() failed: %s' % (sys.exc_info()[1],))
        return self

    def sendMessage(self, outgoingMessage, transportAddress):
        self.__outQueue.append(
            (outgoingMessage, transportAddress)
            )

    # asyncore API
    def handle_connect(self): pass
    def writable(self): return self.__outQueue
    def handle_write(self):
        outgoingMessage, transportAddress = self.__outQueue.pop()
        if isinstance(transportAddress, TransportAddressPair):
            transportAddress = transportAddress.getRemoteAddr()
        debug.logger & debug.flagIO and debug.logger('handle_write: transportAddress %r -> %r outgoingMessage %s' % (self.socket.getsockname(), transportAddress, debug.hexdump(outgoingMessage)))
        try:
            self.socket.sendto(outgoingMessage, transportAddress)
        except socket.error:
            if sys.exc_info()[1].args[0] in sockErrors:
                debug.logger & debug.flagIO and debug.logger('handle_write: ignoring socket error %s' % (sys.exc_info()[1],))
            else:
                raise socket.error(sys.exc_info()[1])
            
    def readable(self): return 1
    def handle_read(self):
        try:
            incomingMessage, transportAddress = self.socket.recvfrom(65535)
            debug.logger & debug.flagIO and debug.logger('handle_read: transportAddress %r -> %r incomingMessage %s' % (transportAddress, self.socket.getsockname(), debug.hexdump(incomingMessage)))
            transportAddress = TransportAddressPair(
                                   self.socket.getsockname(),
                                   transportAddress
                               )
            if not incomingMessage:
                self.handle_close()
                return
            else:
                self._cbFun(self, transportAddress, incomingMessage)
                return
        except socket.error:
            if sys.exc_info()[1].args[0] in sockErrors:
                debug.logger & debug.flagIO and debug.logger('handle_read: known socket error %s' % (sys.exc_info()[1],))
                sockErrors[sys.exc_info()[1].args[0]] and self.handle_close()
                return
            else:
                raise socket.error(sys.exc_info()[1])
    def handle_close(self): pass # no datagram connection
