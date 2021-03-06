import os
import json

import synapse.common as s_common
import synapse.lib.msgpack as s_msgpack
import synapse.lib.jupyter as s_jupyter

import synapse.tests.utils as s_t_utils

class JupyterTest(s_t_utils.SynTest):
    testmods = ['synapse.tests.utils.TestModule']

    async def test_tempcorecmdr(self):
        outp = self.getTestOutp()
        cmdrcore = await s_jupyter.getTempCoreCmdr(self.testmods, outp)
        self.false(cmdrcore.isfini)
        nodes = await cmdrcore.eval('[teststr=beep]', cmdr=True)
        self.len(1, nodes)
        self.eq(nodes[0][0], ('teststr', 'beep'))
        self.true(outp.expect('cli> storm [teststr=beep]'))
        await cmdrcore.fini()
        self.true(cmdrcore.isfini)

    async def test_tempcoreprox(self):
        prox = await s_jupyter.getTempCoreProx(self.testmods)
        self.false(prox.isfini)
        nodes = await s_t_utils.alist(await prox.eval('[teststr=beep]'))
        self.len(1, nodes)
        self.eq(nodes[0][0], ('teststr', 'beep'))
        await prox.fini()
        self.true(prox.isfini)

    async def test_cmdrcore(self):
        async with self.getTestDmon(mirror='dmoncore') as dmon:
            async with await self.agetTestProxy(dmon, 'core') as core:
                outp = self.getTestOutp()
                async with await s_jupyter.CmdrCore.anit(core, outp=outp) as cmdrcore:
                    podes = await cmdrcore.eval('[teststr=beep]',
                                                num=1, cmdr=False)
                    self.len(1, podes)
                    self.false(outp.expect('[teststr=beep]', throw=False))

                    mesgs = await cmdrcore.storm('[teststr=boop]',
                                                 num=1, cmdr=True)
                    self.true(outp.expect('[teststr=boop]', throw=False))
                    podes = [m[1] for m in mesgs if m[0] == 'node']
                    self.gt(len(mesgs), len(podes))
                    self.len(1, podes)
                    self.eq(podes[0][0], ('teststr', 'boop'))

                    # Opts works for cmdr=False
                    podes = await cmdrcore.eval('[teststr=$foo]',
                                                {'vars': {'foo': 'duck'}},
                                                num=1, cmdr=False)
                    self.len(1, podes)
                    self.eq(podes[0][0], ('teststr', 'duck'))
                    # Opts does not work with cmdr=True - we have no way to plumb it through.
                    with self.getAsyncLoggerStream('synapse.cortex',
                                                   'Error during storm execution') as stream:
                        ret = await cmdrcore.eval('[teststr=$foo]',
                                                  {'vars': {'foo': 'fowl'}},
                                                  cmdr=True)
                        await stream.wait(1)
                        self.eq(ret, [])

                    # Assertion based tests
                    podes = await cmdrcore.eval('testint', num=0)
                    self.len(0, podes)
                    podes = await cmdrcore.eval('teststr', num=3)
                    self.len(3, podes)
                    await self.asyncraises(AssertionError, cmdrcore.eval('teststr', num=1))

                    # Feed function for data loading
                    data = [
                        (('testint', 137), {}),
                    ]
                    guid = s_common.guid()
                    ret = await cmdrcore.addFeedData('syn.nodes', data, (guid, 1))
                    self.eq(ret, 2)
                    podes = await cmdrcore.eval('testint=137',
                                                num=1, cmdr=False)
                    self.len(1, podes)

        # Raw cmdline test
        async with self.getTestDmon(mirror='dmoncore') as dmon:
            async with await self.agetTestProxy(dmon, 'core') as core:
                outp = self.getTestOutp()
                async with await s_jupyter.CmdrCore.anit(core, outp=outp) as cmdrcore:
                    await cmdrcore.runCmdLine('help')
                    self.true(outp.expect('cli> help'))
                    self.true(outp.expect('List commands and display help output.'))

    def test_doc_data(self):
        with self.getTestDir() as dirn:
            s_common.gendir(dirn, 'docdata', 'stuff')

            docdata = s_common.genpath(dirn, 'docdata')

            root = s_common.genpath(dirn, 'synapse', 'userguides')

            d = {'key': 'value'}

            s_common.jssave(d, docdata, 'data.json')
            s_common.yamlsave(d, docdata, 'data.yaml')
            s_msgpack.dumpfile(d, os.path.join(docdata, 'data.mpk'))
            with s_common.genfile(docdata, 'stuff', 'data.txt') as fd:
                fd.write('beep'.encode())
            with s_common.genfile(docdata, 'data.jsonl') as fd:
                fd.write(json.dumps(d).encode() + b'\n')
                fd.write(json.dumps(d).encode() + b'\n')
                fd.write(json.dumps(d).encode() + b'\n')

            data = s_jupyter.getDocData('data.json', root)
            self.eq(data, d)
            data = s_jupyter.getDocData('data.yaml', root)
            self.eq(data, d)
            data = s_jupyter.getDocData('data.mpk', root)
            self.eq(data, d)
            data = s_jupyter.getDocData('stuff/data.txt', root)
            self.eq(data, b'beep')
            data = s_jupyter.getDocData('data.jsonl', root)
            self.eq(data, [d, d, d])

            self.raises(ValueError, s_jupyter.getDocData, 'newp.bin', root)
            self.raises(ValueError, s_jupyter.getDocData,
                        '../../../../../../etc/passwd', root)
