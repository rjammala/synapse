import synapse.datamodel as s_datamodel
import synapse.lib.msgpack as s_msgpack

import synapse.tests.utils as s_t_utils

class DataModelTest(s_t_utils.SynTest):

    async def test_datamodel_getModelDef(self):

        async with self.getTestCore() as core:
            modeldef = core.model.getModelDef()

            # Verify it doesn't have any unmarshallable elements
            s_msgpack.en(modeldef)

            for field in ('ctors', 'types', 'forms', 'univs'):
                self.isin(field, modeldef[0][1])
                self.lt(0, len(modeldef[0][1][field]))

            modelinfo = s_datamodel.ModelInfo()
            modelinfo.addDataModels(modeldef)
            self.true(modelinfo.isform('teststr'))
            self.true(modelinfo.isuniv('.seen'))
            self.false(modelinfo.isuniv('seen'))
            self.true(modelinfo.isprop('testtype10:intprop'))
            self.true(modelinfo.isprop('testtype10.seen'))
