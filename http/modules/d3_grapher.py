__author__ = 'mutus'
from twisted.web.template import Element,XMLFile,renderer,flattenString
import numpy as np
import json
from http_server import render_safe

def create1DTestData(len=100):
    '''
    Creates Line plots with "len" points, both a ramp and a random value
    '''
    x_axis = np.arange(len).reshape(len,1)
    rand_y = np.random.randint(len, size=(len,1))
    ramp_y = np.vstack([np.arange(len/2),np.arange(len/2,0,-1)]).reshape(len,1)
    return  np.hstack([x_axis,rand_y]), np.hstack([x_axis,ramp_y])

def create_2d_test_data(indep= 500,dep =300):
    '''
    creates data_vault style 2D data
    :param indep: number of independent points
    :param dep: number of dependent points
    :return: the correct shaped array
    '''

    indeps = np.arange(indep)
    foo=[]
    for i in range(indep):
        for j in range(dep):
            foo.append([i,j])
    foo_arr = np.asarray(foo)
    deps = np.random.randint(256,size=(foo_arr.shape[0],3))
    return np.hstack([foo_arr,deps])

class D3GrapherPage(Element):
    loader = XMLFile('modules/d3_grapher.xml')

    def __init__(self, cxn, request):
        super(D3GrapherPage, self).__init__()

    @render_safe
    def header(self, request, tag):
        return tag('Header.')

    @render_safe
    def footer(self, request, tag):
        return tag('Footer.')

    @render_safe
    def plot_style(self,request,tag):
        '''
        This will eventually be used to set up the style of the plots
        :param request:
        :param tag:
        :return:
        '''
        return tag('CSS GOES HERE')

    @render_safe
    def plot(self,request, tag):
        '''
        This fills d3.js pan-able zoomable plot
        :param request:
        :param tag:
        :return:
        '''
        d = 2 #2 is 2D plot, 1 is 1D plot
        x_min,x_max= 0,100
        y_min,y_max= 0,100
        x_label, y_label = "Independent","Dependent"
        plot_extents = "xMin: %d, xMax: %d, yMin:%d, yMax:%d"%(x_min,x_max,y_min,y_max)
        if d==1:
            test_data, test_data2 = create1DTestData(len=100)
            #I know this is inelegant, but I'm passing zeroes to the frontend for variables that just aren't needed
            # I'm sure there's a better way
            dep_len = 0
            indep_len = 0
            plot_len_2D = "indep_len: %d, dep_len: %d"%(indep_len,dep_len)

        if d==2:
            dep_len = 10
            indep_len = 20
            test_data =  create_2d_test_data(indep=indep_len,dep=dep_len)
            print test_data
            test_1D, test_data2 = create1DTestData(len=100)
            plot_len_2D = "indep_len: %d, dep_len: %d"%(indep_len,dep_len)


        yield (tag.clone().fillSlots(data_ent = json.dumps(test_data.tolist()),data_ent2 = json.dumps(test_data2.tolist()),
                                    plot_extents = plot_extents,
                                    x_label = x_label,
                                    y_label = y_label,
                                    plot_len_2D = plot_len_2D,
                                    plot_dim = str(d)
        ))

class D3GrapherFuncs():
    '''
    This is the class that handles the backend functions
    '''
    def __init__(self):
        pass

page_factory = D3GrapherPage
page_funcs = D3GrapherFuncs()