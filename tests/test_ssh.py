import unittest
from unittest.mock import Mock, patch
from vmforge.provisioners.kali import remote_sudo, change_password, ProvisionError


class Channel:
    def __init__(self, output=b'', errors=b'', code=0, done=True):
        self.output, self.errors, self.code, self.done = output, errors, code, done
        self.closed = False
    def recv_ready(self): return bool(self.output)
    def recv_stderr_ready(self): return bool(self.errors)
    def recv(self, size):
        result, self.output = self.output[:size], self.output[size:]
        return result
    def recv_stderr(self, size):
        result, self.errors = self.errors[:size], self.errors[size:]
        return result
    def exit_status_ready(self): return self.done
    def recv_exit_status(self): return self.code
    def close(self): self.closed = True


class SSHTests(unittest.TestCase):
    def client(self, channel):
        client = Mock()
        client.exec_command.return_value = (Mock(), Mock(channel=channel), Mock())
        return client

    def test_both_streams_drained(self):
        channel = Channel(b'output'*20000, b'warning'*20000)
        client = self.client(channel)
        out = remote_sudo(client, 'private password', 'command')
        self.assertEqual(out, 'output'*20000)
        self.assertTrue(channel.closed)
        self.assertNotIn('private password', client.exec_command.call_args.args[0])

    def test_remote_failure_redacts_password(self):
        channel = Channel(errors=b'failed private password', code=1)
        with self.assertRaises(ProvisionError) as error:
            remote_sudo(self.client(channel), 'private password', 'command')
        self.assertNotIn('private password', str(error.exception))
        self.assertTrue(channel.closed)

    def test_output_limit(self):
        channel = Channel(b'x'*(8*1024**2+1))
        with self.assertRaisesRegex(ProvisionError, 'limite'):
            remote_sudo(self.client(channel), 'password', 'command')
        self.assertTrue(channel.closed)

    def test_timeout(self):
        channel = Channel(done=False)
        with patch('vmforge.provisioners.kali.time.monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(ProvisionError, 'Tempo limite'):
                remote_sudo(self.client(channel), 'password', 'command', timeout=1)
        self.assertTrue(channel.closed)

    def test_password_line_injection(self):
        for password in ('bad\rpassword', 'bad\npassword', 'bad:password'):
            with self.subTest(password=password), patch('vmforge.provisioners.kali.remote_sudo') as command:
                with self.assertRaises(ProvisionError):
                    change_password(Mock(), 'old', password)
                command.assert_not_called()
