import ntpath
import struct
import logging
from .errors import *
from impacket.nmb import NetBIOSError, NetBIOSTimeout
from impacket.smbconnection import SessionError, SMBConnection

# set up logging
log = logging.getLogger('manspider.smb')


class SMBClient:
    '''
    Wrapper around impacket's SMBConnection() object
    '''

    def __init__(self, server, username, password, domain, nthash):

        self.server = server

        self.conn = None

        self.username = username
        self.password = password
        self.domain = domain
        self.nthash = nthash
        if self.nthash:
            self.lmhash = 'aad3b435b51404eeaad3b435b51404ee'
        else:
            self.lmhash = ''


    @property
    def shares(self):

        try:
            resp = self.conn.listShares()
            for i in range(len(resp)):
                sharename = resp[i]['shi1_netname'][:-1]
                log.debug(f'{self.server}: Found share: {sharename}')
                yield sharename
            
        except Exception as e:
            e = handle_impacket_error(e, self)
            log.debug(f'{self.server}: Error listing shares: {e}')
            


    def login(self, refresh=False):
        '''
        Create a new SMBConnection object (if there isn't one already or if refresh is True)
        Attempt to log in, and switch to null session if logon fails
        Return True if logon succeeded
        '''

        if self.conn is None or refresh:
            try:
                self.conn = SMBConnection(self.server, self.server, sess_port=445, timeout=20)
            except Exception as e:
                if type(e) == KeyboardInterrupt:
                    return None
                else:
                    log.debug(impacket_error(e))
                    return None

            try:

                # pass the hash if requested
                if self.nthash and not self.password:
                    self.conn.login(
                        self.username,
                        '',
                        lmhash=self.lmhash,
                        nthash=self.nthash,
                        domain=self.domain,
                    )
                # otherwise, normal login
                else:
                    self.conn.login(
                        self.username,
                        self.password,
                        domain=self.domain,
                    )
            except Exception as e:
                e = handle_impacket_error(e, self, display=True)
                # switch to null session if logon failed and we're not already using null session
                if self.username:
                    if 'LOGON_FAIL' in str(e) or 'PASSWORD_EXPIRED' in str(e):
                        if 'LOGON_FAIL' in str(e):
                            log.warning(f'{self.server}: STATUS_LOGON_FAILURE')
                        log.debug(f'Switching to null session due to error: {e}')
                        self.username = ''
                        self.password = ''
                        self.domain = ''
                        self.nthash = ''
                        self.login(refresh=True)
                        return str(e)

            return True


    def ls(self, share, path):
        '''
        List files in share/path
        Raise FileListError if there's a problem
        '''

        nt_path = ntpath.normpath(f'{path}\\*')

        # for every file/dir in "path"
        try:
            for f in self.conn.listPath(share, nt_path):
                # exclude current and parent directory
                if f.get_longname() not in ['', '.', '..']:
                    yield f
        except Exception as e:
            e = handle_impacket_error(e, self)
            raise FileListError(f'{e.args}: Error listing files at "{share}{nt_path}"')



    def rebuild(self, error=''):
        '''
        Rebuild our SMBConnection() if it gets borked
        '''

        log.debug(f'Rebuilding connection to {self.server} after error: {error}')
        self.login(refresh=True)