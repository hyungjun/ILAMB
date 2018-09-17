from ILAMB.Confrontation import Confrontation
from ILAMB.Confrontation import getVariableList
import matplotlib.pyplot as plt
import ILAMB.Post as post
from scipy.interpolate import CubicSpline
from mpl_toolkits.basemap import Basemap
from ILAMB.Variable import Variable
from netCDF4 import Dataset
import ILAMB.ilamblib as il
import numpy as np
import os,glob
from constants import lbl_months,bnd_months

def DiurnalReshape(time,time_bnds,data):
    dt    = (time_bnds[:,1]-time_bnds[:,0])[:-1]
    dt    = dt.mean()
    spd   = int(round(1./dt))
    begin = np.argmin(time[:(spd-1)]%spd)
    end   = begin+int(time[begin:].size/float(spd))*spd
    shp   = (-1,spd) + data.shape[1:]
    cycle = data[begin:end].reshape(shp)
    t     = time[begin:end].reshape(shp).mean(axis=1)
    return cycle,t

def _findSeasonalTiming(t,x):
    """Return the beginning and ending time of the season of x.

    The data x is assumed to start out relatively small, pass through
    a seasonal period of high values, and then return to small values,
    similar to a bell curve. This routine returns the times where
    these seasonal changes occur. To do this, we accumulate the
    variable x and then try to fit 3 linear segments to each seasonal
    portion. We pose a problem then that finds the breaks which
    minimizes the residual of these three best fit lines.

    Parameters
    ----------
    time: numpy.ndarray
        time array
    x: numpy.ndarray
        a single cycle of data to extract the season from

    Returns
    -------
    tbnds: numpy.ndarray
        the beginning and ending time in an array of size 2
    """
    def cost(t,y):
        from scipy.stats import linregress
        out = linregress(t,y)
        return np.sqrt((((out.slope*t+out.intercept)-y)**2).sum())
    y = x.cumsum()
    b = y.size/2-1
    e = y.size/2+1
    I = np.asarray(range(2,b))
    C = np.zeros(I.shape)
    for a,i in enumerate(I): C[a] = cost(t[:i],y[:i]) + cost(t[i:e],y[i:e])
    b = I[C.argmin()]
    I = np.asarray(range(e,y.size-2))
    C = np.zeros(I.shape)
    for a,i in enumerate(I): C[a] = cost(t[b:i],y[b:i]) + cost(t[i:],y[i:])
    e = I[C.argmin()]
    return t[[b,e]]

def _findSeasonalCentroid(t,x):
    """Return the centroid of the season in polar and cartesian coordinates.

    Parameters
    ----------
    time: numpy.ndarray
        time array but scaled [0,2 pi]
    x: numpy.ndarray
        a single cycle of data to extract the season from

    Returns
    -------
    centroid: numpy.ndarray
        array of size 4, [r,theta,x,y]
    """    
    x0 = (x*np.cos(t/365.*2*np.pi)).mean()
    y0 = (x*np.sin(t/365.*2*np.pi)).mean()
    r0 = np.sqrt(x0*x0+y0*y0)
    a0 = np.arctan2(y0,x0)
    return r0,a0,x0,y0

class ConfDiurnal(Confrontation):
    """A confrontation for examining the diurnal 
    """
    def __init__(self,**keywords):

        # Calls the regular constructor
        super(ConfDiurnal,self).__init__(**keywords)

        # Setup a html layout for generating web views of the results
        pages = []

        # Mean State page
        pages.append(post.HtmlPage("MeanState","Mean State"))
        pages[-1].setHeader("CNAME / RNAME / MNAME")
        pages[-1].setSections(["Diurnal Magnitude"])
        pages.append(post.HtmlAllModelsPage("AllModels","All Models"))
        pages[-1].setHeader("CNAME / RNAME")
        pages[-1].setSections([])
        pages[-1].setRegions(self.regions)
        pages.append(post.HtmlPage("DataInformation","Data Information"))
        pages[-1].setSections([])
        pages[-1].text = "\n"
        with Dataset(self.source) as dset:
            for attr in dset.ncattrs():
                pages[-1].text += "<p><b>&nbsp;&nbsp;%s:&nbsp;</b>%s</p>\n" % (attr,dset.getncattr(attr).encode('ascii','ignore'))
        self.layout = post.HtmlLayout(pages,self.longname)
        
    def stageData(self,m):

        obs = Variable(filename       = self.source,
                       variable_name  = self.variable,
                       alternate_vars = self.alternate_vars)
        if obs.time is None: raise il.NotTemporalVariable()
        self.pruneRegions(obs)
        
        # Try to extract a commensurate quantity from the model
        mod = m.extractTimeSeries(self.variable,
                                  alt_vars     = self.alternate_vars,
                                  expression   = self.derived,
                                  initial_time = obs.time_bnds[ 0,0],
                                  final_time   = obs.time_bnds[-1,1],
                                  lats         = None if obs.spatial else obs.lat,
                                  lons         = None if obs.spatial else obs.lon).convert(obs.unit)
        
        # When we make things comparable, sites can get pruned, we
        # also need to prune the site labels
        lat = np.copy(obs.lat); lon = np.copy(obs.lon)
        obs,mod = il.MakeComparable(obs,mod,clip_ref=True,prune_sites=True,allow_diff_times=True)
        ind = np.sqrt((lat[:,np.newaxis]-obs.lat)**2 +
                      (lon[:,np.newaxis]-obs.lon)**2).argmin(axis=0)
        maxS = max([len(s) for s in self.lbls])
        self.lbls = np.asarray(self.lbls,dtype='S%d' % maxS)[ind]        
        return obs,mod

    def confront(self,m):

        # get the HTML page
        page = [page for page in self.layout.pages if "MeanState" in page.name][0]
        
        # Grab the data
        obs,mod = self.stageData(m)
        Nobs = 365./np.diff(obs.time).mean()
        Nmod = 365./np.diff(mod.time).mean()
        
        # Analysis on a per year basis
        Yobs = (obs.time/365.+1850).astype(int)
        Ymod = (mod.time/365.+1850).astype(int)
        Y    = np.unique(Yobs)
        S1 = []; S2 = []; S3 = []; Lobs = []; Lmod = []
        Sobs = {}; Smod = {}
        for y in Y:

            # Subset the data
            iobs = np.where(y==Yobs)[0]
            imod = np.where(y==Ymod)[0]
            if iobs.size/Nobs < 0.9: continue
            if imod.size/Nmod < 0.9: continue

            # Compute the diurnal magnitude
            vobs,tobs = DiurnalReshape(obs.time     [iobs] % 365,
                                       obs.time_bnds[iobs],
                                       obs.data     [iobs,0])
            vmod,tmod = DiurnalReshape(mod.time     [imod] % 365,
                                       mod.time_bnds[imod],
                                       mod.data     [imod,0])
            vobs  = vobs.max(axis=1)-vobs.min(axis=1)
            vmod  = vmod.max(axis=1)-vmod.min(axis=1)
            Sobs[y] = Variable(name = "season_%d" % y,
                               unit = obs.unit,
                               time = tobs,
                               data = vobs)
            Smod[y] = Variable(name = "season_%d" % y,
                               unit = mod.unit,
                               time = tmod,
                               data = vmod)
            
            # Compute metrics
            To  = _findSeasonalTiming  (tobs,vobs)
            Ro  = _findSeasonalCentroid(tobs,vobs)
            Tm  = _findSeasonalTiming  (tmod,vmod)
            Rm  = _findSeasonalCentroid(tmod,vmod)
            dTo = To[1]-To[0]       # season length of the observation
            a   = np.log(0.1) / 0.5 # 50% relative error equals a score of 1/10
            s1  = np.exp(a* np.abs(To[0]-Tm[0])/dTo)
            s2  = np.exp(a* np.abs(To[1]-Tm[1])/dTo)
            s3  = np.linalg.norm(np.asarray([Ro[2]-Rm[2],Ro[3]-Rm[3]])) #  |Ro - Rm|
            s3 /= np.linalg.norm(np.asarray([      Ro[2],      Ro[3]])) # /|Ro|
            s3  = np.exp(-s3)
            S1.append(s1); S2.append(s2); S3.append(s3)
            Lobs.append(To[1]-To[0])
            Lmod.append(Tm[1]-Tm[0])

        # Score by mean values across years
        S1   = np.asarray(S1  ).mean()
        S2   = np.asarray(S2  ).mean()
        S3   = np.asarray(S3  ).mean()
        Lobs = np.asarray(Lobs).mean()
        Lmod = np.asarray(Lmod).mean()

        with Dataset(os.path.join(self.output_path,"%s_%s.nc" % (self.name,m.name)),mode="w") as results:
            results.setncatts({"name" :m.name, "color":m.color})
            Variable(name = "Season Length global",
                     unit = "d",
                     data = Lmod).toNetCDF4(results,group="MeanState")
            Variable(name = "Season Beginning Score global",
                     unit = "1",
                     data = S1).toNetCDF4(results,group="MeanState")
            Variable(name = "Season Ending Score global",
                     unit = "1",
                     data = S2).toNetCDF4(results,group="MeanState")
            Variable(name = "Season Strength Score global",
                     unit = "1",
                     data = S3).toNetCDF4(results,group="MeanState")
            for key in Smod.keys(): Smod[key].toNetCDF4(results,group="MeanState")
        if not self.master: return
        with Dataset(os.path.join(self.output_path,"%s_Benchmark.nc" % self.name),mode="w") as results:
            results.setncatts({"name" :"Benchmark", "color":np.asarray([0.5,0.5,0.5])})
            Variable(name = "Season Length global",
                     unit = "d",
                     data = Lobs).toNetCDF4(results,group="MeanState")
            for key in Sobs.keys(): Sobs[key].toNetCDF4(results,group="MeanState")

    def determinePlotLimits(self):

        self.limits = {}
        self.limits["season"] = 0.
        for fname in glob.glob(os.path.join(self.output_path,"*.nc")):
            with Dataset(fname) as dataset:
                if "MeanState" not in dataset.groups: continue
                group     = dataset.groups["MeanState"]
                variables = [v for v in group.variables.keys() if v not in group.dimensions.keys()]
                for vname in variables:
                    if "season" in vname:
                        self.limits["season"] = max(self.limits["season"],group.variables[vname].up99)
                    
    def modelPlots(self,m):
        
        bname  = "%s/%s_Benchmark.nc" % (self.output_path,self.name)
        fname  = "%s/%s_%s.nc" % (self.output_path,self.name,m.name)
        if not os.path.isfile(bname): return
        if not os.path.isfile(fname): return

        # get the HTML page
        page = [page for page in self.layout.pages if "MeanState" in page.name][0]
        page.priority = ["Beginning","Ending","Strength","Score","Overall"]

        # list pf plots must be in both the benchmark and the model
        with Dataset(bname) as dset:
            bplts = [key for key in dset.groups["MeanState"].variables.keys() if "season" in key]
        with Dataset(fname) as dset:
            fplts = [key for key in dset.groups["MeanState"].variables.keys() if "season" in key]
        plots = [v for v in bplts if v in fplts]
        plots.sort()

        for plot in plots:

            obs = Variable(filename = bname, variable_name = plot, groupname = "MeanState")
            mod = Variable(filename = fname, variable_name = plot, groupname = "MeanState")
            
            page.addFigure("Diurnal Magnitude",
                           plot,
                           "MNAME_%s.png" % plot,
                           side   = plot.split("_")[-1],
                           legend = False)
            plt.figure(figsize=(5,5),tight_layout=True)
            plt.polar(obs.time/365.*2*np.pi,obs.data,'-k',alpha=0.75)
            plt.polar(mod.time/365.*2*np.pi,mod.data,'-',color=m.color)
            plt.xticks(bnd_months[:-1]/365.*2*np.pi,lbl_months)
            plt.ylim(0,self.limits["season"])
            plt.savefig("%s/%s_%s.png" % (self.output_path,m.name,plot))
            plt.close()
