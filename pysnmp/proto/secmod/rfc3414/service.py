# SNMP v3 USM model services
import time, sys
from pysnmp.proto.secmod.base import AbstractSecurityModel
from pysnmp.proto.secmod.rfc3414.auth import hmacmd5, hmacsha, noauth
from pysnmp.proto.secmod.rfc3414.priv import des, nopriv
from pysnmp.proto.secmod.rfc3826.priv import aes
from pysnmp.proto.secmod.eso.priv import des3, aes192, aes256
from pysnmp.smi.error import NoSuchInstanceError
from pysnmp.proto import rfc1155, errind, error
from pysnmp import debug
from pyasn1.type import univ, namedtype, constraint
from pyasn1.codec.ber import encoder, decoder
from pyasn1.error import PyAsn1Error
from pyasn1.compat.octets import null
    
# USM security params

class UsmSecurityParameters(rfc1155.TypeCoercionHackMixIn, univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('msgAuthoritativeEngineID', univ.OctetString()),
        namedtype.NamedType('msgAuthoritativeEngineBoots', univ.Integer().subtype(subtypeSpec=constraint.ValueRangeConstraint(0, 2147483647))),
        namedtype.NamedType('msgAuthoritativeEngineTime', univ.Integer().subtype(subtypeSpec=constraint.ValueRangeConstraint(0, 2147483647))),
        namedtype.NamedType('msgUserName', univ.OctetString().subtype(subtypeSpec=constraint.ValueSizeConstraint(0, 32))),
        namedtype.NamedType('msgAuthenticationParameters', univ.OctetString()),
        namedtype.NamedType('msgPrivacyParameters', univ.OctetString())
        )

class SnmpUSMSecurityModel(AbstractSecurityModel):
    securityModelID = 3
    authServices = {
        hmacmd5.HmacMd5.serviceID: hmacmd5.HmacMd5(),
        hmacsha.HmacSha.serviceID: hmacsha.HmacSha(),
        noauth.NoAuth.serviceID: noauth.NoAuth()
        }
    privServices = {
        des.Des.serviceID: des.Des(),
        des3.Des3.serviceID: des3.Des3(),        
        aes.Aes.serviceID: aes.Aes(),
        aes192.Aes192.serviceID: aes192.Aes192(),
        aes256.Aes256.serviceID: aes256.Aes256(),
        nopriv.NoPriv.serviceID: nopriv.NoPriv()
        }
    def __init__(self):
        AbstractSecurityModel.__init__(self)
        self.__securityParametersSpec = UsmSecurityParameters()
        self.__timeline = {}
        self.__timelineExpQueue = {}
        self.__expirationTimer = 0
        self.__paramsBranchId = -1

    def __sec2usr(self, snmpEngine,  securityName, securityEngineID=None):
        usmUserEngineID, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('SNMP-USER-BASED-SM-MIB', 'usmUserEngineID')
        if self.__paramsBranchId != usmUserEngineID.branchVersionId:
            usmUserName, usmUserSecurityName = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('SNMP-USER-BASED-SM-MIB', 'usmUserName', 'usmUserSecurityName')

            self.__securityToUserMap = {}

            nextMibNode = usmUserEngineID

            while 1:
                try:
                    nextMibNode = usmUserEngineID.getNextNode(
                                      nextMibNode.name
                                  )
                except NoSuchInstanceError:
                    self.__paramsBranchId = usmUserEngineID.branchVersionId
                    debug.logger & debug.flagSM and debug.logger('_sec2usr: built snmpEngineId + securityName to userName map, version %s: %r' % (self.__paramsBranchId, self.__securityToUserMap))
                    break

                instId = nextMibNode.name[len(usmUserSecurityName.name):]

                __engineID = usmUserEngineID.getNode(usmUserEngineID.name + instId).syntax
                __userName = usmUserName.getNode(usmUserName.name + instId).syntax
                __securityName = usmUserSecurityName.getNode(usmUserSecurityName.name + instId).syntax

                k = __engineID, __securityName

                # first (lesser) securityName wins
                if k not in self.__securityToUserMap:
                    self.__securityToUserMap[k] = __userName

        if securityEngineID is None:
            snmpEngineID, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineID')
            securityEngineID = snmpEngineID.syntax

        try:
            userName = self.__securityToUserMap[(securityEngineID, securityName)]
        except KeyError:
            debug.logger & debug.flagSM and debug.logger('_sec2usr: no entry exists for snmpEngineId %r, securityName %r' % (securityEngineID, securityName))
            raise NoSuchInstanceError()  # emulate MIB lookup
     
        debug.logger & debug.flagSM and debug.logger('_sec2usr: using userName %r for snmpEngineId %r, securityName %r' % (userName, securityEngineID, securityName))

        return userName

    def __getUserInfo(
        self, mibInstrumController, securityEngineID, userName
        ):
        usmUserEntry, = mibInstrumController.mibBuilder.importSymbols(
            'SNMP-USER-BASED-SM-MIB', 'usmUserEntry'
        )
        tblIdx = usmUserEntry.getInstIdFromIndices(
            securityEngineID, userName
        )
        # Get userName & securityName
        usmUserName = usmUserEntry.getNode(
            usmUserEntry.name + (2,) + tblIdx
        ).syntax
        usmUserSecurityName = usmUserEntry.getNode(
            usmUserEntry.name + (3,) + tblIdx
        ).syntax
        # Get protocols
        usmUserAuthProtocol = usmUserEntry.getNode(
            usmUserEntry.name + (5,) + tblIdx
            ).syntax
        usmUserPrivProtocol = usmUserEntry.getNode(
            usmUserEntry.name + (8,) + tblIdx
            ).syntax
        # Get keys
        pysnmpUsmKeyEntry, = mibInstrumController.mibBuilder.importSymbols(
            'PYSNMP-USM-MIB', 'pysnmpUsmKeyEntry'
            )
        pysnmpUsmKeyAuthLocalized = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (1,) + tblIdx
            ).syntax
        pysnmpUsmKeyPrivLocalized = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (2,) + tblIdx
            ).syntax
        return (
            usmUserName,
            usmUserSecurityName,
            usmUserAuthProtocol,
            pysnmpUsmKeyAuthLocalized,
            usmUserPrivProtocol,
            pysnmpUsmKeyPrivLocalized
        )

    def __cloneUserInfo(
            self, mibInstrumController, securityEngineID, userName
        ):
        snmpEngineID, = mibInstrumController.mibBuilder.importSymbols(
            '__SNMP-FRAMEWORK-MIB', 'snmpEngineID'
        )
        # Proto entry
        usmUserEntry, = mibInstrumController.mibBuilder.importSymbols(
            'SNMP-USER-BASED-SM-MIB', 'usmUserEntry'
        )
        tblIdx1 = usmUserEntry.getInstIdFromIndices(
            snmpEngineID.syntax, userName
        )
        # Get proto protocols
        usmUserName = usmUserEntry.getNode(
            usmUserEntry.name + (2,) + tblIdx1
        )
        usmUserSecurityName = usmUserEntry.getNode(
            usmUserEntry.name + (3,) + tblIdx1
        )
        usmUserCloneFrom = usmUserEntry.getNode(
            usmUserEntry.name + (4,) + tblIdx1
        )
        usmUserAuthProtocol = usmUserEntry.getNode(
            usmUserEntry.name + (5,) + tblIdx1
        )
        usmUserPrivProtocol = usmUserEntry.getNode(
            usmUserEntry.name + (8,) + tblIdx1
        )
        # Get proto keys
        pysnmpUsmKeyEntry, = mibInstrumController.mibBuilder.importSymbols(
            'PYSNMP-USM-MIB', 'pysnmpUsmKeyEntry'
        )
        pysnmpUsmKeyAuth = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (3,) + tblIdx1
        )
        pysnmpUsmKeyPriv = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (4,) + tblIdx1
        )        
        
        # Create new row from proto values

        tblIdx2 = usmUserEntry.getInstIdFromIndices(
            securityEngineID, userName
        )

        # New row
        mibInstrumController.writeVars(
            ((usmUserEntry.name + (13,) + tblIdx2, 4),)
        )

        # Set user&securityNames
        usmUserEntry.getNode(
            usmUserEntry.name + (2,) + tblIdx2
        ).syntax = usmUserName.syntax
        usmUserEntry.getNode(
            usmUserEntry.name + (3,) + tblIdx2
        ).syntax = usmUserSecurityName.syntax

        # Store a reference to original row
        usmUserEntry.getNode(
            usmUserEntry.name + (4,) + tblIdx2
        ).syntax = usmUserCloneFrom.syntax.clone(tblIdx1)
 
        # Set protocols
        usmUserEntry.getNode(
            usmUserEntry.name + (5,) + tblIdx2
        ).syntax = usmUserAuthProtocol.syntax
        usmUserEntry.getNode(
            usmUserEntry.name + (8,) + tblIdx2
        ).syntax = usmUserPrivProtocol.syntax
       
        # Localize and set keys
        pysnmpUsmKeyEntry, = mibInstrumController.mibBuilder.importSymbols(
            'PYSNMP-USM-MIB', 'pysnmpUsmKeyEntry'
            )
        pysnmpUsmKeyAuthLocalized = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (1,) + tblIdx2
            )
        if usmUserAuthProtocol.syntax in self.authServices:
            localizeKey = self.authServices[usmUserAuthProtocol.syntax].localizeKey
            localAuthKey = localizeKey(
                pysnmpUsmKeyAuth.syntax,
                securityEngineID
                )
        else:
            raise error.StatusInformation(
                errorIndication = errind.unsupportedAuthProtocol
                )
        if localAuthKey is not None:
            pysnmpUsmKeyAuthLocalized.syntax = pysnmpUsmKeyAuthLocalized.syntax.clone(localAuthKey)
        pysnmpUsmKeyPrivLocalized = pysnmpUsmKeyEntry.getNode(
            pysnmpUsmKeyEntry.name + (2,) + tblIdx2
            )
        if usmUserPrivProtocol.syntax in self.privServices:
            localizeKey = self.privServices[usmUserPrivProtocol.syntax].localizeKey
            localPrivKey = localizeKey(
                usmUserAuthProtocol.syntax,
                pysnmpUsmKeyPriv.syntax,
                securityEngineID
                )
        else:
            raise error.StatusInformation(
                errorIndication = errind.unsupportedPrivProtocol
                )
        if localPrivKey is not None:
            pysnmpUsmKeyPrivLocalized.syntax = pysnmpUsmKeyPrivLocalized.syntax.clone(localPrivKey)
        return (
            usmUserName.syntax,
            usmUserSecurityName.syntax,
            usmUserAuthProtocol.syntax,
            pysnmpUsmKeyAuthLocalized.syntax,
            usmUserPrivProtocol.syntax,
            pysnmpUsmKeyPrivLocalized.syntax
        )
              
    def __generateRequestOrResponseMsg(
        self,
        snmpEngine,
        messageProcessingModel,
        globalData,
        maxMessageSize,
        securityModel,
        securityEngineID,
        securityName,
        securityLevel,
        scopedPDU,
        securityStateReference
        ):
        snmpEngineID = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineID')[0].syntax
        # 3.1.1
        if securityStateReference is not None:
            # 3.1.1a
            cachedSecurityData = self._cache.pop(securityStateReference)
            usmUserName = cachedSecurityData['msgUserName']
            if 'usmUserSecurityName' in cachedSecurityData:
                usmUserSecurityName = cachedSecurityData['usmUserSecurityName']
            else:
                usmUserSecurityName = usmUserName
            if 'usmUserAuthProtocol' in cachedSecurityData:
                usmUserAuthProtocol = cachedSecurityData['usmUserAuthProtocol']
            else:
                usmUserAuthProtocol = noauth.NoAuth.serviceID
            if 'usmUserAuthKeyLocalized' in cachedSecurityData:
                usmUserAuthKeyLocalized = cachedSecurityData['usmUserAuthKeyLocalized']
            else:
                usmUserAuthKeyLocalized = None
            if 'usmUserPrivProtocol' in cachedSecurityData:
                usmUserPrivProtocol = cachedSecurityData['usmUserPrivProtocol']
            else:
                usmUserPrivProtocol = nopriv.NoPriv.serviceID
            if 'usmUserPrivKeyLocalized' in cachedSecurityData:
                usmUserPrivKeyLocalized = cachedSecurityData['usmUserPrivKeyLocalized']
            else:
                usmUserPrivKeyLocalized = None
            securityEngineID = snmpEngineID
            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: user info read from cache')
        elif securityName:
            # 3.1.1b
            try:
                ( usmUserName,
                  usmUserSecurityName,
                  usmUserAuthProtocol,
                  usmUserAuthKeyLocalized,
                  usmUserPrivProtocol,
                  usmUserPrivKeyLocalized ) = self.__getUserInfo(
                    snmpEngine.msgAndPduDsp.mibInstrumController,
                    securityEngineID,
                    self.__sec2usr(snmpEngine, securityName, securityEngineID)
                )
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: read user info')
            except NoSuchInstanceError:
                pysnmpUsmDiscovery, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__PYSNMP-USM-MIB', 'pysnmpUsmDiscovery')
                __reportUnknownName = not pysnmpUsmDiscovery.syntax
                if not __reportUnknownName:
                    try:
                        ( usmUserName,
                          usmUserSecurityName,
                          usmUserAuthProtocol,
                          usmUserAuthKeyLocalized,
                          usmUserPrivProtocol,
                          usmUserPrivKeyLocalized ) = self.__cloneUserInfo(
                            snmpEngine.msgAndPduDsp.mibInstrumController,
                            securityEngineID,
                            self.__sec2usr(snmpEngine, securityName)
                        )
                    except NoSuchInstanceError:
                        __reportUnknownName = 1

                if __reportUnknownName:
                    raise error.StatusInformation(
                        errorIndication = errind.unknownSecurityName
                        )
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: clone user info')
        else:
            # empty username used for engineID discovery
            usmUserName = usmUserSecurityName = null
            usmUserAuthProtocol = noauth.NoAuth.serviceID
            usmUserPrivProtocol = nopriv.NoPriv.serviceID
            usmUserAuthKeyLocalized = usmUserPrivKeyLocalized = None
            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: use empty USM data')
            
        debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: local usmUserName %r usmUserSecurityName %r usmUserAuthProtocol %s usmUserPrivProtocol %s securityEngineID %r securityName %r' % (usmUserName, usmUserSecurityName, usmUserAuthProtocol, usmUserPrivProtocol, securityEngineID, securityName))

        msg = globalData
        
        # 3.1.2
        if securityLevel == 3:
            if usmUserAuthProtocol == noauth.NoAuth.serviceID or \
               usmUserPrivProtocol == nopriv.NoPriv.serviceID:
                raise error.StatusInformation(
                    errorIndication = errind.unsupportedSecurityLevel
                    )

        # 3.1.3
        if securityLevel == 3 or securityLevel == 2:
            if usmUserAuthProtocol == noauth.NoAuth.serviceID:
                raise error.StatusInformation(
                    errorIndication = errind.unsupportedSecurityLevel
                    )

        securityParameters = self.__securityParametersSpec

        scopedPDUData = msg.setComponentByPosition(3).getComponentByPosition(3)
        scopedPDUData.setComponentByPosition(
            0, scopedPDU, verifyConstraints=False
            )
        
        # 3.1.6a
        if securityStateReference is None and (  # request type check added
            securityLevel == 3 or securityLevel == 2
            ):
            if securityEngineID in self.__timeline:
                ( snmpEngineBoots,
                  snmpEngineTime,
                  latestReceivedEngineTime,
                  latestUpdateTimestamp) = self.__timeline[
                    securityEngineID
                    ]
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: read snmpEngineBoots, snmpEngineTime from timeline')
            else:
                # 2.3 XXX is this correct?
                snmpEngineBoots = snmpEngineTime = 0
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: no timeline for securityEngineID %r' % (securityEngineID,))
        # 3.1.6.b
        elif securityStateReference is not None:  # XXX Report?
            ( snmpEngineBoots,
              snmpEngineTime ) = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineBoots', 'snmpEngineTime')
            snmpEngineBoots = snmpEngineBoots.syntax
            snmpEngineTime = snmpEngineTime.syntax.clone()
            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: read snmpEngineBoots, snmpEngineTime from LCD')
        # 3.1.6.c
        else:
            snmpEngineBoots = snmpEngineTime = 0
            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: assuming zero snmpEngineBoots, snmpEngineTime')

        debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: use snmpEngineBoots %s snmpEngineTime %s for securityEngineID %r' % (snmpEngineBoots, snmpEngineTime, securityEngineID))

        # 3.1.4a
        if securityLevel == 3:
            if usmUserPrivProtocol in self.privServices:
                privHandler = self.privServices[usmUserPrivProtocol]
            else:
                raise error.StatusInformation(
                    errorIndication = errind.encryptionError
                )

            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: scopedPDU %s' % scopedPDU.prettyPrint())

            try:
                dataToEncrypt = encoder.encode(scopedPDU)
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: scopedPDU serialization error: %s' % sys.exc_info()[1])
                raise error.StatusInformation(
                    errorIndication = errind.serializationError
                )
            
            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: scopedPDU encoded into %s' % debug.hexdump(dataToEncrypt))

            ( encryptedData,
              privParameters ) = privHandler.encryptData(
                usmUserPrivKeyLocalized,
                ( snmpEngineBoots, snmpEngineTime, None ),
                dataToEncrypt
            )

            securityParameters.setComponentByPosition(
                5, privParameters, verifyConstraints=False
            )
            scopedPDUData.setComponentByPosition(
                1, encryptedData, verifyConstraints=False
            )

            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: scopedPDU ciphered into %s' % debug.hexdump(encryptedData))

        # 3.1.4b
        elif securityLevel == 1 or securityLevel == 2:
            securityParameters.setComponentByPosition(5, '')

        debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: %s' % scopedPDUData.prettyPrint())
        
        # 3.1.5
        securityParameters.setComponentByPosition(
            0, securityEngineID, verifyConstraints=False
        )
        securityParameters.setComponentByPosition(
            1, snmpEngineBoots, verifyConstraints=False
        )
        securityParameters.setComponentByPosition(
            2, snmpEngineTime, verifyConstraints=False
        )
    
        # 3.1.7
        securityParameters.setComponentByPosition(
            3, usmUserName, verifyConstraints=False
        )

        # 3.1.8a
        if securityLevel == 3 or securityLevel == 2:
            if usmUserAuthProtocol in self.authServices:
                authHandler = self.authServices[usmUserAuthProtocol]
            else:
                raise error.StatusInformation(
                    errorIndication = errind.authenticationFailure
                    )

            # extra-wild hack to facilitate BER substrate in-place re-write
            securityParameters.setComponentByPosition(
                4, '\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                )

            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: %s' % (securityParameters.prettyPrint(),))
            
            try:
                msg.setComponentByPosition(2, encoder.encode(securityParameters), verifyConstraints=False)
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: securityParameters serialization error: %s' % sys.exc_info()[1])
                raise error.StatusInformation(
                    errorIndication = errind.serializationError
                )

            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: auth outgoing msg: %s' % msg.prettyPrint())

            try:
                wholeMsg = encoder.encode(msg)
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: msg serialization error: %s' % sys.exc_info()[1])
                raise error.StatusInformation(
                    errorIndication = errind.serializationError
                )

            authenticatedWholeMsg = authHandler.authenticateOutgoingMsg(
                usmUserAuthKeyLocalized, wholeMsg
                )

        # 3.1.8b
        else:
            securityParameters.setComponentByPosition(
                4, '', verifyConstraints=False
                )

            debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: %s' % (securityParameters.prettyPrint(),))

            try:
                msg.setComponentByPosition(2, encoder.encode(securityParameters), verifyConstraints=False)
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: secutiryParameters serialization error: %s' % sys.exc_info()[1])
                raise error.StatusInformation(
                    errorIndication = errind.serializationError
                )

            try:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: plain outgoing msg: %s' % msg.prettyPrint())
                authenticatedWholeMsg = encoder.encode(msg)
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: msg serialization error: %s' % sys.exc_info()[1])
                raise error.StatusInformation(
                    errorIndication = errind.serializationError
                )

        debug.logger & debug.flagSM and debug.logger('__generateRequestOrResponseMsg: %s outgoing msg: %s' % (securityLevel > 1 and "authenticated" or "plain", debug.hexdump(authenticatedWholeMsg)))

        # 3.1.9
        return (
            msg.getComponentByPosition(2),
            authenticatedWholeMsg
            )

    def generateRequestMsg(
        self,
        snmpEngine,
        messageProcessingModel,
        globalData,
        maxMessageSize,
        securityModel,
        securityEngineID,
        securityName,
        securityLevel,
        scopedPDU,
        ):
        return self.__generateRequestOrResponseMsg(
            snmpEngine,
            messageProcessingModel,
            globalData,
            maxMessageSize,
            securityModel,
            securityEngineID,
            securityName,
            securityLevel,
            scopedPDU,
            None
            )
    
    def generateResponseMsg(
        self,
        snmpEngine,
        messageProcessingModel,
        globalData,
        maxMessageSize,
        securityModel,
        securityEngineID,
        securityName,
        securityLevel,
        scopedPDU,
        securityStateReference
        ):
        return self.__generateRequestOrResponseMsg(
            snmpEngine,
            messageProcessingModel,
            globalData,
            maxMessageSize,
            securityModel,
            securityEngineID,
            securityName,
            securityLevel,
            scopedPDU,
            securityStateReference
            )
            
    # 3.2
    def processIncomingMsg(
        self,
        snmpEngine,
        messageProcessingModel,
        maxMessageSize,
        securityParameters,
        securityModel,
        securityLevel,
        wholeMsg,
        msg  # XXX 
        ):
        # 3.2.9 -- moved up here to be able to report
        # maxSizeResponseScopedPDU on error
        # (48 - maximum SNMPv3 header length)
        maxSizeResponseScopedPDU = int(maxMessageSize) - len(securityParameters) - 48

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: securityParameters %s' % debug.hexdump(securityParameters))

        # 3.2.1 
        try:
            securityParameters, rest = decoder.decode(
                securityParameters,
                asn1Spec=self.__securityParametersSpec
                )
        except PyAsn1Error:
            debug.logger & debug.flagSM and debug.logger('processIncomingMsg: %s' % (sys.exc_info()[1],))
            snmpInASNParseErrs, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMPv2-MIB', 'snmpInASNParseErrs')
            snmpInASNParseErrs.syntax = snmpInASNParseErrs.syntax + 1
            raise error.StatusInformation(
                errorIndication=errind.parseError
                )

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: %s' % (securityParameters.prettyPrint(),))

        # 3.2.2
        msgAuthoritativeEngineID = securityParameters.getComponentByPosition(0)
        securityStateReference = self._cache.push(
            msgUserName=securityParameters.getComponentByPosition(3)
            )

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: cache write securityStateReference %s by msgUserName %s' % (securityStateReference, securityParameters.getComponentByPosition(3)))
        
        scopedPduData = msg.getComponentByPosition(3)

        # Used for error reporting
        contextEngineId = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineID')[0].syntax
        contextName = null

        # 3.2.3
        if msgAuthoritativeEngineID not in self.__timeline:
            debug.logger & debug.flagSM and debug.logger('processIncomingMsg: unknown securityEngineID %r' % (msgAuthoritativeEngineID,))
            if not msgAuthoritativeEngineID:
                # 3.2.3b
                usmStatsUnknownEngineIDs, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsUnknownEngineIDs')
                usmStatsUnknownEngineIDs.syntax = usmStatsUnknownEngineIDs.syntax+1
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: null securityEngineID')
                pysnmpUsmDiscoverable, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__PYSNMP-USM-MIB', 'pysnmpUsmDiscoverable')
                if pysnmpUsmDiscoverable.syntax:
                    debug.logger & debug.flagSM and debug.logger('processIncomingMsg: request EngineID discovery')

                    # Report original contextName
                    if scopedPduData.getName() != 'plaintext':
                        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: scopedPduData not plaintext %s' % scopedPduData.prettyPrint())
                        raise error.StatusInformation(
                            errorIndication = errind.unknownEngineID
                            )

                    # 7.2.6.a.1 
                    scopedPdu = scopedPduData.getComponent()
                    contextEngineId = scopedPdu.getComponentByPosition(0)
                    contextName = scopedPdu.getComponentByPosition(1)

                    raise error.StatusInformation(
                        errorIndication = errind.unknownEngineID,
                        oid=usmStatsUnknownEngineIDs.name,
                        val=usmStatsUnknownEngineIDs.syntax,
                        securityStateReference=securityStateReference,
                        securityLevel=securityLevel,
                        contextEngineId=contextEngineId,
                        contextName=contextName,
                        scopedPDU=scopedPdu,
                        maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                        )
                else:
                    debug.logger & debug.flagSM and debug.logger('processIncomingMsg: will not discover EngineID')                    
                    # free securityStateReference XXX
                    raise error.StatusInformation(
                        errorIndication = errind.unknownEngineID
                        )

        snmpEngineID = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineID')[0].syntax
 
        msgUserName = securityParameters.getComponentByPosition(3)

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: read from securityParams msgAuthoritativeEngineID %r msgUserName %r' % (msgAuthoritativeEngineID, msgUserName))
        
        if msgUserName:
            # 3.2.4
            try:
                ( usmUserName,
                  usmUserSecurityName,
                  usmUserAuthProtocol,
                  usmUserAuthKeyLocalized,
                  usmUserPrivProtocol,
                  usmUserPrivKeyLocalized ) = self.__getUserInfo(
                    snmpEngine.msgAndPduDsp.mibInstrumController,
                    msgAuthoritativeEngineID,
                    msgUserName
                )
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: read user info from LCD')
            except NoSuchInstanceError:
                pysnmpUsmDiscoverable, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__PYSNMP-USM-MIB', 'pysnmpUsmDiscoverable')
                __reportUnknownName = not pysnmpUsmDiscoverable.syntax
                if not __reportUnknownName:
                    try:
                        ( usmUserName,
                          usmUserSecurityName,
                          usmUserAuthProtocol,
                          usmUserAuthKeyLocalized,
                          usmUserPrivProtocol,
                          usmUserPrivKeyLocalized ) = self.__cloneUserInfo(
                            snmpEngine.msgAndPduDsp.mibInstrumController,
                            msgAuthoritativeEngineID,
                            msgUserName
                        )
                        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: cloned user info')
                    except NoSuchInstanceError:
                        __reportUnknownName = 1
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: unknown securityEngineID %r msgUserName %r' % (msgAuthoritativeEngineID, msgUserName))
                if __reportUnknownName:
                    usmStatsUnknownUserNames, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsUnknownUserNames')
                    usmStatsUnknownUserNames.syntax = usmStatsUnknownUserNames.syntax+1
                    raise error.StatusInformation(
                        errorIndication = errind.unknownSecurityName,
                        oid = usmStatsUnknownUserNames.name,
                        val = usmStatsUnknownUserNames.syntax,
                        securityStateReference=securityStateReference,
                        securityLevel=securityLevel,
                        contextEngineId=contextEngineId,
                        contextName=contextName,
                        maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                        )
        else:
            # empty username used for engineID discovery
            usmUserName = usmUserSecurityName = null
            usmUserAuthProtocol = noauth.NoAuth.serviceID
            usmUserPrivProtocol = nopriv.NoPriv.serviceID
            usmUserAuthKeyLocalized = usmUserPrivKeyLocalized = None

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: now have usmUserName %r usmUserSecurityName %r usmUserAuthProtocol %r usmUserPrivProtocol %r for msgUserName %r' % (usmUserName, usmUserSecurityName, usmUserAuthProtocol, usmUserPrivProtocol, msgUserName))

        # 3.2.11 (moved up here to let Reports be authenticated & encrypted)
        self._cache.pop(securityStateReference)
        securityStateReference = self._cache.push(
            msgUserName=securityParameters.getComponentByPosition(3),
            usmUserSecurityName=usmUserSecurityName,
            usmUserAuthProtocol=usmUserAuthProtocol,
            usmUserAuthKeyLocalized=usmUserAuthKeyLocalized,
            usmUserPrivProtocol=usmUserPrivProtocol,
            usmUserPrivKeyLocalized=usmUserPrivKeyLocalized
        )

        # 3.2.5
        if msgAuthoritativeEngineID == snmpEngineID:
            # Authoritative SNMP engine: make sure securityLevel is sufficient
            __badSecIndication = None
            if securityLevel == 3:
                if usmUserAuthProtocol == noauth.NoAuth.serviceID:
                    __badSecIndication = 'authPriv wanted while auth not expected'
                if usmUserPrivProtocol == nopriv.NoPriv.serviceID:
                    __badSecIndication = 'authPriv wanted while priv not expected'
            elif securityLevel == 2:
                if usmUserAuthProtocol == noauth.NoAuth.serviceID:
                    __badSecIndication = 'authNoPriv wanted while auth not expected'
                if usmUserPrivProtocol != nopriv.NoPriv.serviceID:
                    __badSecIndication = 'authNoPriv wanted while priv expected'

            elif securityLevel == 1:
                if usmUserAuthProtocol != noauth.NoAuth.serviceID:
                    __badSecIndication = 'noAuthNoPriv wanted while auth expected'
                if usmUserPrivProtocol != nopriv.NoPriv.serviceID:
                    __badSecIndication = 'noAuthNoPriv wanted while priv expected'
            if __badSecIndication:
                usmStatsUnsupportedSecLevels, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsUnsupportedSecLevels')
                usmStatsUnsupportedSecLevels.syntax = usmStatsUnsupportedSecLevels.syntax + 1
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: reporting inappropriate security level for user %s: %s' % (msgUserName, __badSecIndication))
                raise error.StatusInformation(
                    errorIndication=errind.unsupportedSecurityLevel,
                    oid=usmStatsUnsupportedSecLevels.name,
                    val=usmStatsUnsupportedSecLevels.syntax,
                    securityStateReference=securityStateReference,
                    securityLevel=securityLevel,
                    contextEngineId=contextEngineId,
                    contextName=contextName,
                    maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                    )

        # 3.2.6
        if securityLevel == 3 or securityLevel == 2:
            if usmUserAuthProtocol in self.authServices:
                authHandler = self.authServices[usmUserAuthProtocol]
            else:
                raise error.StatusInformation(
                    errorIndication = errind.authenticationFailure
                    )
            try:
                authenticatedWholeMsg = authHandler.authenticateIncomingMsg(
                    usmUserAuthKeyLocalized,
                    securityParameters.getComponentByPosition(4),
                    wholeMsg
                    )
            except error.StatusInformation:
                usmStatsWrongDigests, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsWrongDigests')
                usmStatsWrongDigests.syntax = usmStatsWrongDigests.syntax+1
                raise error.StatusInformation(
                    errorIndication = errind.authenticationFailure,
                    oid=usmStatsWrongDigests.name,
                    val=usmStatsWrongDigests.syntax,
                    securityStateReference=securityStateReference,
                    securityLevel=securityLevel,
                    contextEngineId=contextEngineId,
                    contextName=contextName,
                    maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                    )
            
            debug.logger & debug.flagSM and debug.logger('processIncomingMsg: incoming msg authenticated')

            if msgAuthoritativeEngineID:
                # 3.2.3a moved down here to execute only for authed msg
                self.__timeline[msgAuthoritativeEngineID] = (
                    securityParameters.getComponentByPosition(1),
                    securityParameters.getComponentByPosition(2),
                    securityParameters.getComponentByPosition(2),
                    int(time.time())
                    )
                
                expireAt = int(self.__expirationTimer + 300 / snmpEngine.transportDispatcher.getTimerResolution())
                if expireAt not in self.__timelineExpQueue:
                    self.__timelineExpQueue[expireAt] = []
                self.__timelineExpQueue[expireAt].append(
                    msgAuthoritativeEngineID
                    )
                    
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: store timeline for securityEngineID %r' % (msgAuthoritativeEngineID,))
            
        # 3.2.7
        if securityLevel == 3 or securityLevel == 2:
            if msgAuthoritativeEngineID == snmpEngineID:
                # Authoritative SNMP engine: use local notion (SF bug #1649032)
                ( snmpEngineBoots,
                  snmpEngineTime ) = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-FRAMEWORK-MIB', 'snmpEngineBoots', 'snmpEngineTime')
                snmpEngineBoots = snmpEngineBoots.syntax
                snmpEngineTime = snmpEngineTime.syntax.clone()
                idleTime = 0
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: read snmpEngineBoots (%s), snmpEngineTime (%s) from LCD' % (snmpEngineBoots, snmpEngineTime))
            else:
                # Non-authoritative SNMP engine: use cached estimates
                if msgAuthoritativeEngineID in self.__timeline:
                    ( snmpEngineBoots,
                      snmpEngineTime,
                      latestReceivedEngineTime,
                      latestUpdateTimestamp ) = self.__timeline[
                        msgAuthoritativeEngineID
                        ]
                    # time passed since last talk with this SNMP engine
                    idleTime = int(time.time())-latestUpdateTimestamp
                    debug.logger & debug.flagSM and debug.logger('processIncomingMsg: read timeline snmpEngineBoots %s snmpEngineTime %s for msgAuthoritativeEngineID %r, idle time %s secs' % (snmpEngineBoots, snmpEngineTime, msgAuthoritativeEngineID, idleTime))
                else:
                    raise error.ProtocolError('Peer SNMP engine info missing')

            msgAuthoritativeEngineBoots = securityParameters.getComponentByPosition(1)
            msgAuthoritativeEngineTime = securityParameters.getComponentByPosition(2)

            # 3.2.7a
            if msgAuthoritativeEngineID == snmpEngineID:
                if snmpEngineBoots == 2147483647 or \
                   snmpEngineBoots != msgAuthoritativeEngineBoots or \
                   abs(idleTime + int(snmpEngineTime) - \
                       int(msgAuthoritativeEngineTime)) > 150:
                    usmStatsNotInTimeWindows, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsNotInTimeWindows')
                    usmStatsNotInTimeWindows.syntax = usmStatsNotInTimeWindows.syntax+1
                    raise error.StatusInformation(
                        errorIndication = errind.notInTimeWindow,
                        oid=usmStatsNotInTimeWindows.name,
                        val=usmStatsNotInTimeWindows.syntax,
                        securityStateReference=securityStateReference,
                        securityLevel=2,
                        contextEngineId=contextEngineId,
                        contextName=contextName,
                        maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                        )
            # 3.2.7b
            else:
                # 3.2.7b.1
                if msgAuthoritativeEngineBoots > snmpEngineBoots or \
                   msgAuthoritativeEngineBoots == snmpEngineBoots and \
                   msgAuthoritativeEngineTime > latestReceivedEngineTime:
                    self.__timeline[msgAuthoritativeEngineID] = (
                        msgAuthoritativeEngineBoots,
                        msgAuthoritativeEngineTime,
                        msgAuthoritativeEngineTime,
                        int(time.time())
                        )
                    expireAt = int(self.__expirationTimer + 300 / snmpEngine.transportDispatcher.getTimerResolution())
                    if expireAt not in self.__timelineExpQueue:
                        self.__timelineExpQueue[expireAt] = []
                    self.__timelineExpQueue[expireAt].append(
                        msgAuthoritativeEngineID
                        )

                    debug.logger & debug.flagSM and debug.logger('processIncomingMsg: stored timeline msgAuthoritativeEngineBoots %s msgAuthoritativeEngineTime %s for msgAuthoritativeEngineID %r' % (msgAuthoritativeEngineBoots, msgAuthoritativeEngineTime, msgAuthoritativeEngineID))
                    
                # 3.2.7b.2
                if snmpEngineBoots == 2147483647 or \
                   msgAuthoritativeEngineBoots < snmpEngineBoots or \
                   msgAuthoritativeEngineBoots == snmpEngineBoots and \
                   abs(idleTime + int(snmpEngineTime) - \
                       int(msgAuthoritativeEngineTime)) > 150:
                    raise error.StatusInformation(
                        errorIndication = errind.notInTimeWindow
                        )

        # 3.2.8a
        if securityLevel == 3:
            if usmUserPrivProtocol in self.privServices:
                privHandler = self.privServices[usmUserPrivProtocol]
            else:
                raise error.StatusInformation(
                    errorIndication = errind.decryptionError
                    )
            encryptedPDU = scopedPduData.getComponentByPosition(1)
            if encryptedPDU is None: # no ciphertext
                raise error.StatusInformation(
                    errorIndication = errind.decryptionError
                    )

            try:
                decryptedData = privHandler.decryptData(
                    usmUserPrivKeyLocalized,
                        ( securityParameters.getComponentByPosition(1),
                          securityParameters.getComponentByPosition(2),
                          securityParameters.getComponentByPosition(5) ),
                        encryptedPDU
                    )
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: PDU deciphered into %s' % debug.hexdump(decryptedData))
            except error.StatusInformation:
                usmStatsDecryptionErrors, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsDecryptionErrors')
                usmStatsDecryptionErrors.syntax = usmStatsDecryptionErrors.syntax+1
                raise error.StatusInformation(
                    errorIndication = errind.decryptionError,
                    oid=usmStatsDecryptionErrors.name,
                    val=usmStatsDecryptionErrors.syntax,
                    securityStateReference=securityStateReference,
                    securityLevel=securityLevel,
                    contextEngineId=contextEngineId,
                    contextName=contextName,
                    maxSizeResponseScopedPDU=maxSizeResponseScopedPDU
                    )
            scopedPduSpec = scopedPduData.setComponentByPosition(0).getComponentByPosition(0)
            try:
                scopedPDU, rest = decoder.decode(
                    decryptedData, asn1Spec=scopedPduSpec
                    )
            except PyAsn1Error:
                debug.logger & debug.flagSM and debug.logger('processIncomingMsg: scopedPDU decoder failed %s' % sys.exc_info()[0])                
                raise error.StatusInformation(
                    errorIndication = errind.decryptionError
                    )
        else:
            # 3.2.8b
            scopedPDU = scopedPduData.getComponentByPosition(0)
            if scopedPDU is None:  # no plaintext
                raise error.StatusInformation(
                    errorIndication = errind.decryptionError
                    )

        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: scopedPDU decoded %s' % scopedPDU.prettyPrint()) 

        # 3.2.10
        securityName = usmUserSecurityName
        
        debug.logger & debug.flagSM and debug.logger('processIncomingMsg: cached msgUserName %s info by securityStateReference %s' % (msgUserName, securityStateReference))
        
        # Delayed to include details
        if not msgUserName and not msgAuthoritativeEngineID:
            usmStatsUnknownUserNames, = snmpEngine.msgAndPduDsp.mibInstrumController.mibBuilder.importSymbols('__SNMP-USER-BASED-SM-MIB', 'usmStatsUnknownUserNames')
            usmStatsUnknownUserNames.syntax = usmStatsUnknownUserNames.syntax+1
            raise error.StatusInformation(
                errorIndication=errind.unknownSecurityName,
                oid=usmStatsUnknownUserNames.name,
                val=usmStatsUnknownUserNames.syntax,
                securityStateReference=securityStateReference,
                securityEngineID=msgAuthoritativeEngineID,
                securityLevel=securityLevel,
                contextEngineId=contextEngineId,
                contextName=contextName,
                maxSizeResponseScopedPDU=maxSizeResponseScopedPDU,
                PDU=scopedPDU
                )

        # 3.2.12
        return ( msgAuthoritativeEngineID,
                 securityName,
                 scopedPDU,
                 maxSizeResponseScopedPDU,
                 securityStateReference )

    def __expireTimelineInfo(self):
        if self.__expirationTimer in self.__timelineExpQueue:
            for engineIdKey in self.__timelineExpQueue[self.__expirationTimer]:
                if engineIdKey in self.__timeline:
                    del self.__timeline[engineIdKey]
                    debug.logger & debug.flagSM and debug.logger('__expireTimelineInfo: expiring %r' % (engineIdKey,))
            del self.__timelineExpQueue[self.__expirationTimer]
        self.__expirationTimer = self.__expirationTimer + 1
        
    def receiveTimerTick(self, snmpEngine, timeNow):
        self.__expireTimelineInfo()
