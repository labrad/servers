from __future__ import absolute_import

import datavault.backend as backend
import datavault.util
import numpy as np
import pytest
import tempfile
import os

def test_create_ex_backend():
    fname = tempfile.mktemp(suffix='.hdf5')
    try:
        indep = [backend.Independent(label='ilabel1', shape=[1], datatype='v', unit=''),
                 backend.Independent(label='ilabel2', shape=[1], datatype='v', unit='')]
        dep = [backend.Dependent(label='dlabel', legend='dlegend1', shape=[1], datatype='v', unit=''),
               backend.Dependent(label='dlabel', legend='dlegend2', shape=[1], datatype='v', unit='')]
        dvfile = backend.create_backend(fname[:-5], "Test of datavault", indep, dep, extended=True)

        rec_array = datavault.util.to_record_array(np.eye(4))
        dvfile.addData(rec_array)
        rec_array_tr = np.core.records.fromarrays((np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4))
        dvfile.addData(rec_array_tr)
        assert len(dvfile) == 8
        data, newpos = dvfile.getData(limit=8, start=0, transpose=False, simpleOnly=True)
        data = datavault.util.from_record_array(data)
        ref_data = np.vstack((np.eye(4), np.array([np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4]).T))
        assert np.array_equal(data, ref_data)
    finally:
        unlink_if_exist(fname)

def test_create_simple_backend():
    try:
        fname = tempfile.mktemp(suffix='.hdf5')
        indep = [backend.Independent(label='ilabel1', shape=[1], datatype='v', unit=''),
                 backend.Independent(label='ilabel2', shape=[1], datatype='v', unit='')]
        dep = [backend.Dependent(label='dlabel', legend='dlegend1', shape=[1], datatype='v', unit=''),
               backend.Dependent(label='dlabel', legend='dlegend2', shape=[1], datatype='v', unit='')]
        dvfile = backend.create_backend(fname[:-5], "Test of datavault", indep, dep, extended=False)

        rec_array = datavault.util.to_record_array(np.eye(4))
        dvfile.addData(rec_array)
        rec_array_tr = np.core.records.fromarrays((np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4))
        dvfile.addData(rec_array_tr)
        data, newpos = dvfile.getData(limit=8, start=0, transpose=False, simpleOnly=True)
        data = datavault.util.from_record_array(data)
        ref_data = np.vstack((np.eye(4), np.array([np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4]).T))
        assert np.array_equal(data, ref_data)
    finally:
        unlink_if_exist(fname)

def test_create_csv_backend():
    indep = [backend.Independent(label='ilabel1', shape=[1], datatype='v', unit=''),
             backend.Independent(label='ilabel2', shape=[1], datatype='v', unit='')]
    dep = [backend.Dependent(label='dlabel', legend='dlegend1', shape=[1], datatype='v', unit=''),
           backend.Dependent(label='dlabel', legend='dlegend2', shape=[1], datatype='v', unit='')]

    csv_filename = tempfile.mktemp(suffix='.csv')
    ini_filename = csv_filename[:-4] + '.ini'
    try:
        dataset = backend.CsvNumpyData(csv_filename)
        dataset.initialize_info('test CSV dataset', indep, dep)
        dataset.save()
        rec_array = datavault.util.to_record_array(np.eye(4))
        dataset.addData(rec_array)
        rec_array_tr = np.core.records.fromarrays((np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4))
        dataset.addData(rec_array_tr)
        dataset.save()
        del dataset
        dataset = backend.open_backend(csv_filename[:-4])
        data, newpos = dataset.getData(limit=8, start=0, transpose=False, simpleOnly=True)
        data = datavault.util.from_record_array(data)
        ref_data = np.vstack((np.eye(4), np.array([np.ones(4)*1, np.ones(4)*2, np.ones(4)*3, np.ones(4)*4]).T))
        assert np.array_equal(data, ref_data)
        assert os.path.exists(csv_filename)
        assert os.path.exists(ini_filename)
    finally:
        unlink_if_exist(ini_filename, csv_filename)

def unlink_if_exist(*names):
    for name in names:
        try:
            os.unlink(name)
        except OSError:
            pass
