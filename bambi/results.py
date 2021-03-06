import pandas as pd
import numpy as np
import pymc3 as pm
from pymc3.model import TransformedRV
import pymc3.diagnostics as pmd
from abc import abstractmethod, ABCMeta
import re, warnings


class ModelResults(object):

    '''
    Base class for ModelResults hierarchy.
    Args:
        model (Model): a bambi Model instance specifying the model.
    '''

    __metaclass__ = ABCMeta

    def __init__(self, model):

        self.model = model
        self.terms = list(model.terms.values())
        self.diagnostics = model._diagnostics \
            if hasattr(model, '_diagnostics') else None
        self.n_terms = len(model.terms)

    @abstractmethod
    def plot(self):
        pass

    @abstractmethod
    def summary(self):
        pass


class PyMC3Results(ModelResults):

    '''
    Holds PyMC3 sampler results and provides plotting and summarization tools.
    Args:
        model (Model): a bambi Model instance specifying the model.
        trace (MultiTrace): a PyMC3 MultiTrace object returned by the sampler. 
    '''

    def __init__(self, model, trace):

        self.trace = trace
        self.n_samples = len(trace)

        # here we determine which variables have been internally transformed 
        # (e.g., sd_log). transformed vars are actually 'untransformed' from 
        # the PyMC3 model's perspective, and it's the backtransformed (e.g., sd)
        # variable that is 'transformed'. So the logic of this is to find and
        # remove 'untranformed' variables that have a 'transformed' counterpart,
        # in that 'untransformed' varname is the 'transfornmed' varname plus
        # some suffix (such as '_log' or '_interval')
        rvs = model.backend.model.unobserved_RVs
        trans = set(var.name for var in rvs if isinstance(var, TransformedRV))
        untrans = set(var.name for var in rvs) - trans
        untrans = set(x for x in untrans if not any([t in x for t in trans]))
        self.untransformed_vars = [x for x in trace.varnames \
            if x in trans | untrans]

        super(PyMC3Results, self).__init__(model)


    def _filter_names(self, names, exclude_ranefs=True, hide_transformed=True):
        names = self.untransformed_vars \
            if hide_transformed else self.trace.varnames
        # helper function to put parameter names in same format as random_terms
        def _format(name):
            regex = re.match(r'^u_([^\|]+)\|([^_\1]+)_\1(.*_sd$)?', name)
            return name if regex is None or regex.group(3) is not None \
                else 'u_{}|{}'.format(regex.group(1), regex.group(2))
        if exclude_ranefs:
            names = [x for x in names
                if _format(x)[2:] not in list(self.model.random_terms.keys())]
        return names

    def _prettify_name(self, old_name):
        # re1 chops 'u_subj__7' into {1:'u_', 2:'subj', 3:'7'}
        re1 = re.match(r'^([bu]_)(.+[^__\d+]+)(__\d+)?$', old_name)
        # params like the residual SD will have no matches, so just return
        if re1 is None:
            return old_name
        # handle random slopes first because their format is weird.
        # re2 chops 'x|subj_x[a]' into {1:'x', 2:'subj', 3:'x', 4:'[a]'}
        re2 = re.match(r'^([^\|]+)\|([^_\1]+)(_\1)?(\[.+\])?$', re1.group(2))
        if re2 is not None:
            term = self.model.terms['{}|{}'.format(re2.group(1), re2.group(2))]
            # random slopes of factors
            if re2.group(4) is not None:
                return '{}{}|{}'.format(re2.group(3)[1:],
                    re2.group(4), term.levels[int(re1.group(3)[2:])])
            # random slopes of continuous predictors
            else:
                return '{}|{}'.format(
                    re2.group(1), term.levels[int(re1.group(3)[2:])])
        # handle SD terms
        # re3 chops 'u_x|subj_x[a]_sd' into {'x', '|subj', '_x', '[a]'}
        re3 = re.match(r'^([^\|]+)(\|[^_\1]+)?(_\1)?(\[\d+\])?_sd$',
            re1.group(2))
        if re1.group(3) is None and re3 is not None:
            if re3.group(2) is None: return '1|{}_sd'.format(re3.group(1))
            if re3.group(4) is not None: return '{}{}{}_sd'.format(
                re3.group(3)[1:], re3.group(4), re3.group(2))
            return '{}{}_sd'.format(re3.group(1), re3.group(2))
        # handle fixed effects and random intercepts
        term = self.model.terms[re1.group(2)]
        if re1.group(1)=='b_': return re1.group(2) if re1.group(3) is None \
            else term.levels[int(re1.group(3)[2:])]
        if re1.group(1)=='u_':
            return '1|{}[{}]'.format(
                re1.group(2), term.levels[int(re1.group(3)[2:])])

    def plot(self, burn_in=0, names=None, annotate=True, exclude_ranefs=False, 
        hide_transformed=True, kind='trace', **kwargs):
        '''
        Plots posterior distributions and sample traces. Basically a wrapper
        for pm.traceplot() plus some niceties, based partly on code from:
        https://pymc-devs.github.io/pymc3/notebooks/GLM-model-selection.html
        Args:
            burn_in (int): Number of initial samples to exclude before
                summary statistics are computed.
            names (list): Optional list of variable names to summarize.
            annotate (bool): If True (default), add lines marking the
                posterior means, write the posterior means next to the
                lines, and add factor level names for fixed factors with
                more than one distribution on the traceplot.
            exclude_ranefs (bool): If True, do not show trace plots for
                individual random effects. Defaults to False.
            hide_transformed (bool): If True (default), do not show trace
                plots for internally transformed variables.
            kind (str): Either 'trace' (default) or 'priors'. If 'priors',
                this just internally calls Model.plot()
        '''
        if kind == 'priors':
            return self.model.plot()

        # if no 'names' specified, filter out unwanted variables
        if names is None:
            names = self._filter_names(names, exclude_ranefs, hide_transformed)

        # compute means for all variables and factors
        if annotate:
            kwargs['lines'] = {param: self.trace[param, burn_in:].mean() \
                for param in names}
            # factors (fixed terms with shape > 1) must be handled separately
            factors = {}
            for fix in self.model.fixed_terms.values():
                if 'b_'+fix.name in names and len(fix.levels)>1:
                    # remove factor from dictionary of lines to plot
                    kwargs['lines'].pop('b_'+fix.name)
                    # add factor and its column means to dictionary of factors
                    factors.update({'b_'+fix.name:
                        {':'.join(re.findall('\[([^]]+)\]', x)):
                         self.trace['b_'+fix.name, burn_in:].mean(0)[i]
                         for i,x in enumerate(fix.levels)}})

        # make the traceplot
        ax = pm.traceplot(self.trace[burn_in:], varnames=names,
            figsize=(12,len(names)*1.5), **kwargs)

        if annotate:
            # add lines and annotation for the factors
            for f in factors.keys():
                for lev in factors[f]:
                    # draw line
                    ax[names.index(f),0].axvline(x=factors[f][lev],
                        color="r", lw=1.5)
                    # write the mean
                    ax[names.index(f),0].annotate(
                        '{:.2f}'.format(factors[f][lev]),
                        xy=(factors[f][lev],0), xycoords='data', xytext=(5,10),
                        textcoords='offset points', rotation=90, va='bottom',
                        fontsize='large', color='#AA0022')
                    # write the factor level name
                    ax[names.index(f),0].annotate(lev,
                        xy=(factors[f][lev],0), xycoords='data', xytext=(-11,5),
                        textcoords='offset points', rotation=90, va='bottom',
                        fontsize='large', color='#AA0022')
            # add lines and annotation for the rest of the variables
            for v in kwargs['lines'].keys():
                ax[names.index(v),0].annotate(
                    '{:.2f}'.format(kwargs['lines'][v]),
                    xy=(kwargs['lines'][v],0), xycoords='data', xytext=(5,10),
                    textcoords='offset points', rotation=90, va='bottom',
                    fontsize='large', color='#AA0022')

        # For binomial models with n_trials = 1 (most common use case),
        # tell user which event is being modeled
        if self.model.family.name=='binomial' and \
            np.max(self.model.y.data) < 1.01:
            event = next(i for i,x in enumerate(self.model.y.data.flatten()) \
                if x>.99)
            warnings.warn('Modeling the probability that {}==\'{}\''.format(
                self.model.y.name,
                str(self.model.data[self.model.y.name][event])))

        return ax

    def summary(self, burn_in=0, exclude_ranefs=True, names=None,
                hide_transformed=True, mc_error=False, **kwargs):
        '''
        Summarizes all parameter estimates. Basically a wrapper for
        pm.df_summary() plus some niceties.
        Args:
            burn_in (int): Number of initial samples to exclude before
                summary statistics are computed.
            exclude_ranefs (bool): If True (default), do not print
                summary statistics for individual random effects.
            names (list): Optional list of variable names to summarize.
            hide_transformed (bool): If True (default), do not print
                summary statistics for internally transformed variables.
            mc_error (bool): If True (defaults to False), include the monte
                carlo error for each parameter estimate.
        '''

        # if no 'names' specified, filter out unwanted variables
        if names is None:
            names = self._filter_names(names, exclude_ranefs, hide_transformed)

        # get the basic DataFrame
        df = pm.df_summary(self.trace[burn_in:], varnames=names, **kwargs)
        df.set_index([[self._prettify_name(x) for x in df.index]], inplace=True)

        # append diagnostic info if there are multiple chains.
        if self.trace.nchains > 1:
            # first remove unwanted variables so we don't waste time on those
            diag_trace = self.trace[burn_in:]
            for var in set(diag_trace.varnames) - set(names):
                diag_trace.varnames.remove(var)
            # append each diagnostic statistic
            for diag_fn,diag_name in zip([pmd.effective_n, pmd.gelman_rubin],
                                         ['effective_n',   'gelman_rubin']):
                # compute the diagnostic statistic
                stat = diag_fn(diag_trace)
                # rename stat indices to match df indices
                for k, v in list(stat.items()):
                    stat.pop(k)
                    # handle categorical predictors w/ >3 levels
                    if isinstance(v, np.ndarray) and len(v) > 1:
                        for i,x in enumerate(v):
                            ugly_name = '{}__{}'.format(k, i)
                            stat[self._prettify_name(ugly_name)] = x
                    # handle all other variables
                    else:
                        stat[self._prettify_name(k)] = v
                # append to df
                stat = pd.DataFrame(stat, index=[diag_name]).T
                df = df.merge(stat, how='left', left_index=True, right_index=True)
        else:
            warnings.warn('Multiple MCMC chains (i.e., njobs > 1) are required'
                          ' in order to compute convergence diagnostics.')

        # drop the mc_error column if requested
        if not mc_error:
            df = df.drop('mc_error', axis=1)

        # For binomial models with n_trials = 1 (most common use case),
        # tell user which event is being modeled
        if self.model.family.name=='binomial' and \
            np.max(self.model.y.data) < 1.01:
            event = next(i for i,x in enumerate(self.model.y.data.flatten()) \
                if x>.99)
            warnings.warn('Modeling the probability that {}==\'{}\''.format(
                self.model.y.name,
                str(self.model.data[self.model.y.name][event])))

        return df

    def get_trace(self, burn_in=0, names=None, exclude_ranefs=True,
        hide_transformed=True):
        '''
        Returns the MCMC samples in a nice, neat DataFrame.
        Args:
            burn_in (int): Number of initial samples to exclude from
                each chain before returning the trace DataFrame.
            names (list): Optional list of variable names to get samples for.
            exclude_ranefs (bool): If True (default), do not return samples
                for individual random effects.
            hide_transformed (bool): If True (default), do not return
            samples for internally transformed variables.
        '''
        # if no 'names' specified, filter out unwanted variables
        if names is None:
            names = self._filter_names(names, exclude_ranefs, hide_transformed)

        # helper function to label the trace DataFrame columns appropriately
        def get_cols(var):
            # handle terms with a single level
            if len(self.trace[var].shape)==1 or self.trace[var].shape[1]==1:
                return [self._prettify_name(var)]
            else:
                # handle fixed terms with multiple levels
                # (slice off the 'b_' or 'u_')
                if var[2:] in self.model.fixed_terms.keys():
                    return self.model.terms[var[2:]].levels
                # handle random terms with multiple levels
                else:
                    return ['{}[{}]'.format(var[2:], x)
                            for x in self.model.terms[var[2:]].levels]

        # construct the trace DataFrame
        trace_df = pd.concat([pd.DataFrame(self.trace[x, burn_in:],
                                           columns=get_cols(x))
                              for x in names], axis=1)

        return trace_df


class PyMC3ADVIResults(ModelResults):
    '''
    Holds PyMC3 ADVI results and provides plotting and summarization tools.
    Args:
        model (Model): a bambi Model instance specifying the model.
        params (MultiTrace): ADVI parameters returned by PyMC3.
    '''
    def __init__(self, model, params):

        self.means = params['means']
        self.sds = params['stds']
        self.elbo_vals = params['elbo_vals']
        super(PyMC3ADVIResults, self).__init__(model)
