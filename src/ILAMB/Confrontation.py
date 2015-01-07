import numpy as np

class Confrontation():
    """
    A class for confronting model results with observational data.
    """
    def __init__(self,path):
        """
        This is all info that would need to be extracted from the
        observational data file and/or the configure file.
        """
        self.path = path
        mml       = np.genfromtxt("%s/monthly_mlo.csv" % path,delimiter=",",skip_header=57)
        self.t    = (mml[:,3]-1850)*365 # days since 00:00:00 1/1/1850
        self.var  = np.ma.masked_where(mml[:,4]<0,mml[:,4])
        self.lat  = 19.4
        self.lon  = 24.4
        self.variable = "co2"
        self.metric = {}
        self.metric["Annual Mean"]    = []
        self.metric["Seasonal Cycle"] = []
        self.metric["Interannual Variability"] = []
        self.metric["Trend"] = []
        self.metric["Trend"].append("")

    def extractModelResult(self,M):
        """
        Extracts the model result on the time interval needed for this confrontation.

        Parameters
        ----------
        M : ILAMB.ModelResult.ModelResult
            the model results

        Returns
        -------
        t,var : numpy.ndarray
            the time series of the variable on the confrontation time interval
        """
        t,var = M.extractPointTimeSeries(self.variable,
                                         self.lat,
                                         self.lon,
                                         initial_time=self.t.min(),
                                         final_time  =self.t.max())
        return t,var

    def computeNRMSE(self,M,t=[],var=[]):
        """


        """
        # if data wasn't passed in, grab it now
        if not (np.asarray(t).size or np.asarray(var).size):
            t,var = M.extractPointTimeSeries(self.variable,
                                             self.lat,
                                             self.lon,
                                             initial_time=self.t.min(),
                                             final_time  =self.t.max())
        
        