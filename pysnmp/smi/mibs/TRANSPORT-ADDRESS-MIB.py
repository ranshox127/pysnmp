# PySNMP SMI module. Autogenerated from smidump -f python TRANSPORT-ADDRESS-MIB
# by libsmi2pysnmp-0.0.3-alpha at Mon May 23 20:07:53 2005,
# Python version (2, 4, 0, 'final', 0)

# Imported just in case new ASN.1 types would be created
from pyasn1.type import constraint, namedval

# Imports

( Integer, ObjectIdentifier, OctetString, ) = mibBuilder.importSymbols("ASN1", "Integer", "ObjectIdentifier", "OctetString")
( Bits, Integer32, ModuleIdentity, MibIdentifier, ObjectIdentity, TimeTicks, mib_2, ) = mibBuilder.importSymbols("SNMPv2-SMI", "Bits", "Integer32", "ModuleIdentity", "MibIdentifier", "ObjectIdentity", "TimeTicks", "mib-2")
( TextualConvention, ) = mibBuilder.importSymbols("SNMPv2-TC", "TextualConvention")

# Types

class TransportAddress(OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(0,255)
    pass

class TransportAddressDns(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(1,255)
    pass

class TransportAddressIPv4(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(6,6)
    pass

class TransportAddressIPv4z(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(10,10)
    pass

class TransportAddressIPv6(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(18,18)
    pass

class TransportAddressIPv6z(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(22,22)
    pass

class TransportAddressLocal(TextualConvention, OctetString):
    subtypeSpec = OctetString.subtypeSpec+constraint.ValueRangeConstraint(1,255)
    pass

class TransportAddressType(Integer):
    subtypeSpec = Integer.subtypeSpec+constraint.SingleValueConstraint(12,9,14,2,7,1,8,0,11,15,16,3,4,10,6,5,13,)
    namedValues = namedval.NamedValues(("unknown", 0), ("udpIpv4", 1), ("sctpIpv6", 10), ("sctpIpv4z", 11), ("sctpIpv6z", 12), ("local", 13), ("udpDns", 14), ("tcpDns", 15), ("sctpDns", 16), ("udpIpv6", 2), ("udpIpv4z", 3), ("udpIpv6z", 4), ("tcpIpv4", 5), ("tcpIpv6", 6), ("tcpIpv4z", 7), ("tcpIpv6z", 8), ("sctpIpv4", 9), )
    pass

class TransportDomain(ObjectIdentifier):
    pass


# Objects

transportAddressMIB = ModuleIdentity((1, 3, 6, 1, 2, 1, 100))
transportDomains = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1))
transportDomainUdpIpv4 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 1))
transportDomainUdpIpv6 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 2))
transportDomainUdpIpv4z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 3))
transportDomainUdpIpv6z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 4))
transportDomainTcpIpv4 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 5))
transportDomainTcpIpv6 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 6))
transportDomainTcpIpv4z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 7))
transportDomainTcpIpv6z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 8))
transportDomainSctpIpv4 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 9))
transportDomainSctpIpv6 = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 10))
transportDomainSctpIpv4z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 11))
transportDomainSctpIpv6z = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 12))
transportDomainLocal = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 13))
transportDomainUdpDns = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 14))
transportDomainTcpDns = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 15))
transportDomainSctpDns = MibIdentifier((1, 3, 6, 1, 2, 1, 100, 1, 16))

# Augmentions

# Exports

# Types
mibBuilder.exportSymbols("TRANSPORT-ADDRESS-MIB", TransportAddress=TransportAddress, TransportAddressDns=TransportAddressDns, TransportAddressIPv4=TransportAddressIPv4, TransportAddressIPv4z=TransportAddressIPv4z, TransportAddressIPv6=TransportAddressIPv6, TransportAddressIPv6z=TransportAddressIPv6z, TransportAddressLocal=TransportAddressLocal, TransportAddressType=TransportAddressType, TransportDomain=TransportDomain)

# Objects
mibBuilder.exportSymbols("TRANSPORT-ADDRESS-MIB", transportAddressMIB=transportAddressMIB, transportDomains=transportDomains, transportDomainUdpIpv4=transportDomainUdpIpv4, transportDomainUdpIpv6=transportDomainUdpIpv6, transportDomainUdpIpv4z=transportDomainUdpIpv4z, transportDomainUdpIpv6z=transportDomainUdpIpv6z, transportDomainTcpIpv4=transportDomainTcpIpv4, transportDomainTcpIpv6=transportDomainTcpIpv6, transportDomainTcpIpv4z=transportDomainTcpIpv4z, transportDomainTcpIpv6z=transportDomainTcpIpv6z, transportDomainSctpIpv4=transportDomainSctpIpv4, transportDomainSctpIpv6=transportDomainSctpIpv6, transportDomainSctpIpv4z=transportDomainSctpIpv4z, transportDomainSctpIpv6z=transportDomainSctpIpv6z, transportDomainLocal=transportDomainLocal, transportDomainUdpDns=transportDomainUdpDns, transportDomainTcpDns=transportDomainTcpDns, transportDomainSctpDns=transportDomainSctpDns)

