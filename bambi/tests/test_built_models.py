import pytest
from bambi.models import Term, Model
from bambi.priors import Prior
import pandas as pd
import numpy as np
import matplotlib
import re
matplotlib.use('Agg')


@pytest.fixture(scope="module")
def crossed_data():
    '''
    Random effects:
    10 subjects, 12 items, 5 sites
    Subjects crossed with items, nested in sites
    Items crossed with sites

    Fixed effects:
    A continuous predictor, a numeric dummy, and a three-level category
    (levels a,b,c)

    Structure:
    Subjects nested in dummy (e.g., gender), crossed with threecats
    Items crossed with dummy, nested in threecats
    Sites partially crossed with dummy (4/5 see a single dummy, 1/5 sees both
    dummies)
    Sites crossed with threecats
    '''
    from os.path import dirname, join
    data_dir = join(dirname(__file__), 'data')
    data = pd.read_csv(join(data_dir, 'crossed_random.csv'))
    return data


def test_empty_model(crossed_data):
    # using formula
    model0 = Model(crossed_data)
    model0.add_y('Y')
    model0.build()
    model0.fit(samples=1)

    # using add_term
    model1 = Model(crossed_data)
    model1.fit('Y ~ 0', run=False)
    model1.build()
    model1.fit(samples=1)

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)


def test_nan_handling(crossed_data):
    data = crossed_data.copy()

    # Should fail because predictor has NaN
    model_fail_na = Model(crossed_data)
    model_fail_na.fit('Y ~ continuous', run=False)
    model_fail_na.terms['continuous'].data[[4, 6, 8], :] = np.nan
    with pytest.raises(ValueError):
        model_fail_na.build()

    # Should drop 3 rows with warning
    model_drop_na = Model(crossed_data, dropna=True)
    model_drop_na.fit('Y ~ continuous', run=False)
    model_drop_na.terms['continuous'].data[[4, 6, 8], :] = np.nan
    with pytest.warns(UserWarning) as w:
        model_drop_na.build()
    assert '3 rows' in w[0].message.args[0]


def test_intercept_only_model(crossed_data):
    # using formula
    model0 = Model(crossed_data)
    model0.fit('Y ~ 1', run=False)
    model0.build()
    model0.fit(samples=1)

    # using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    model1.add_intercept()
    model1.build()
    model1.fit(samples=1)

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)


def test_slope_only_model(crossed_data):
    # using formula
    model0 = Model(crossed_data)
    model0.fit('Y ~ 0 + continuous', run=False)
    model0.build()
    model0.fit(samples=1)

    # using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    model1.add_term('continuous')
    model1.build()
    model1.fit(samples=1)

    # check that term names agree
    assert set(model0.term_names) == set(model1.term_names)

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)


def test_cell_means_parameterization(crossed_data):
    # build model using formula
    model0 = Model(crossed_data)
    model0.fit('Y ~ 0 + threecats', run=False)
    model0.build()
    model0.fit(samples=1)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    model1.add_term('threecats', drop_first=False)
    model1.build()
    model1.fit(samples=1)

    # check that design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)


def test_3x4_fixed_anova(crossed_data):
    # add a four-level category that's perfectly crossed with threecats
    crossed_data['fourcats'] = sum(
        [[x]*10 for x in ['a', 'b', 'c', 'd']], list())*3

    # using formula, with intercept
    model0 = Model(crossed_data)
    model0.fit('Y ~ threecats*fourcats', run=False)
    model0.build()
    fitted0 = model0.fit(samples=1)
    # make sure X has 11 columns (not including the intercept)
    assert len(fitted0.diagnostics['VIF']) == 11

    # using formula, without intercept (i.e., 2-factor cell means model)
    model1 = Model(crossed_data)
    model1.fit('Y ~ 0 + threecats*fourcats', run=False)
    model1.build()
    fitted1 = model1.fit(samples=1)
    # make sure X has 12 columns
    assert len(fitted1.diagnostics['VIF']) == 12


def test_cell_means_with_covariate(crossed_data):
    # build model using formula
    model0 = Model(crossed_data)
    model0.fit('Y ~ 0 + threecats + continuous', run=False)
    model0.build()
    # model0.fit(samples=1)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    model1.add_term('threecats', drop_first=False)
    model1.add_term('continuous')
    model1.build()
    # model1.fit(samples=1)

    # check that design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that threecats priors have finite variance
    assert not any(np.isinf(model0.terms['threecats'].prior.args['sd']))

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)


def test_many_fixed_many_random(crossed_data):
    # build model using formula
    model0 = Model(crossed_data)
    fitted = model0.fit('Y ~ continuous + dummy + threecats',
               random=['0+threecats|subj', '1|item', '0+continuous|item',
                       'dummy|item', 'threecats|site'], samples=10)
    # model0.build()
    # model0.fit(samples=1)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    # fixed effects
    model1.add_intercept()
    model1.add_term('continuous')
    model1.add_term('dummy')
    model1.add_term('threecats')
    # random effects
    model1.add_term('threecats', over='subj', drop_first=False, random=True,
                    categorical=True)
    model1.add_term('item', random=True, categorical=True, drop_first=False)
    model1.add_term('continuous', over='item', random=True)
    model1.add_term('dummy', over='item', random=True)
    model1.add_term('site', random=True, categorical=True, drop_first=False)
    model1.add_term('threecats', over='site', random=True, categorical=True)
    model1.build()
    # model1.fit(samples=1)

    # check that the random effects design matrices have the same shape
    X0 = pd.concat([pd.DataFrame(t.data) if not isinstance(t.data, dict) else
                    pd.concat([pd.DataFrame(t.data[x])
                               for x in t.data.keys()], axis=1)
                    for t in model0.random_terms.values()], axis=1)
    X1 = pd.concat([pd.DataFrame(t.data) if not isinstance(t.data, dict) else
                    pd.concat([pd.DataFrame(t.data[x])
                               for x in t.data.keys()], axis=1)
                    for t in model0.random_terms.values()], axis=1)
    assert X0.shape == X1.shape

    # check that the random effect design matrix contain the same columns,
    # even if term names / columns names / order of columns is different
    X0_set = set(tuple(X0.iloc[:, i]) for i in range(len(X0.columns)))
    X1_set = set(tuple(X1.iloc[:, i]) for i in range(len(X1.columns)))
    assert X0_set == X1_set

    # check that fixed effect design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)

    # check that add_formula and add_term models have same priors for random
    # effects
    priors0 = {x.name: x.prior.args[
        'sd'].args for x in model0.terms.values() if x.random}
    priors1 = {x.name: x.prior.args[
        'sd'].args for x in model1.terms.values() if x.random}
    assert set(priors0) == set(priors1)

    # test consistency between summary and get_trace
    assert len(set(fitted.get_trace().columns)) == 15
    assert set(fitted.get_trace().columns)==set(fitted.summary().index)

    # check hide_transformed
    # it looks like some versions of pymc3 add a trailing '_' to transformed
    # vars and some dont. so here for consistency we strip out any trailing '_'
    # that we find
    full = fitted.summary(exclude_ranefs=False, hide_transformed=False).index
    full = set([re.sub(r'_$', r'', x) for x in full])
    test_set = fitted.summary(exclude_ranefs=False).index
    test_set = set([re.sub(r'_$', r'', x) for x in test_set])
    answer = {'Y_sd_interval',
     'u_continuous|item_sd_log',
     'u_dummy|item_sd_log',
     'u_item_sd_log',
     'u_site_sd_log',
     'u_threecats|site_threecats[0]_sd_log',
     'u_threecats|site_threecats[1]_sd_log',
     'u_threecats|subj_threecats[0]_sd_log',
     'u_threecats|subj_threecats[1]_sd_log',
     'u_threecats|subj_threecats[2]_sd_log'}
    assert full.difference(test_set) == answer

    # check exclude_ranefs
    test_set = fitted.summary(hide_transformed=False).index
    test_set = set([re.sub(r'_$', r'', x) for x in test_set])
    answer = {'1|item[0]','1|item[10]','1|item[11]','1|item[1]','1|item[2]',
        '1|item[3]','1|item[4]','1|item[5]','1|item[6]','1|item[7]','1|item[8]',
        '1|item[9]','1|site[0]','1|site[1]','1|site[2]','1|site[3]','1|site[4]',
        'continuous|item[0]','continuous|item[10]','continuous|item[11]',
        'continuous|item[1]','continuous|item[2]','continuous|item[3]',
        'continuous|item[4]','continuous|item[5]','continuous|item[6]',
        'continuous|item[7]','continuous|item[8]','continuous|item[9]',
        'dummy|item[0]','dummy|item[10]','dummy|item[11]','dummy|item[1]',
        'dummy|item[2]','dummy|item[3]','dummy|item[4]','dummy|item[5]',
        'dummy|item[6]','dummy|item[7]','dummy|item[8]','dummy|item[9]',
        'threecats[0]|site[0]','threecats[0]|site[1]','threecats[0]|site[2]',
        'threecats[0]|site[3]','threecats[0]|site[4]','threecats[0]|subj[0]',
        'threecats[0]|subj[1]','threecats[0]|subj[2]','threecats[0]|subj[3]',
        'threecats[0]|subj[4]','threecats[0]|subj[5]','threecats[0]|subj[6]',
        'threecats[0]|subj[7]','threecats[0]|subj[8]','threecats[0]|subj[9]',
        'threecats[1]|site[0]','threecats[1]|site[1]','threecats[1]|site[2]',
        'threecats[1]|site[3]','threecats[1]|site[4]','threecats[1]|subj[0]',
        'threecats[1]|subj[1]','threecats[1]|subj[2]','threecats[1]|subj[3]',
        'threecats[1]|subj[4]','threecats[1]|subj[5]','threecats[1]|subj[6]',
        'threecats[1]|subj[7]','threecats[1]|subj[8]','threecats[1]|subj[9]',
        'threecats[2]|subj[0]','threecats[2]|subj[1]','threecats[2]|subj[2]',
        'threecats[2]|subj[3]','threecats[2]|subj[4]','threecats[2]|subj[5]',
        'threecats[2]|subj[6]','threecats[2]|subj[7]','threecats[2]|subj[8]',
        'threecats[2]|subj[9]','u_threecats|site_threecats[0]_sd_log',
        'u_threecats|site_threecats[1]_sd_log',
        'u_threecats|subj_threecats[0]_sd_log',
        'u_threecats|subj_threecats[1]_sd_log',
        'u_threecats|subj_threecats[2]_sd_log'}
    assert full.difference(test_set) == answer

    # test plots
    fitted.plot(kind='priors')
    fitted.plot()


def test_cell_means_with_many_random_effects(crossed_data):
    # build model using formula
    model0 = Model(crossed_data)
    model0.fit('Y ~ 0 + threecats',
               random=['0+threecats|subj', 'continuous|item', 'dummy|item',
                       'threecats|site'], run=False)
    model0.build()
    # model0.fit(samples=1)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('Y')
    # fixed effects
    model1.add_term('threecats', drop_first=False)
    # random effects
    model1.add_term('threecats', over='subj', drop_first=False, random=True,
                    categorical=True)
    model1.add_term('item', random=True, categorical=True, drop_first=False)
    model1.add_term('continuous', over='item', random=True)
    model1.add_term('dummy', over='item', random=True)
    model1.add_term('site', random=True, categorical=True, drop_first=False)
    model1.add_term('threecats', over='site', random=True, categorical=True)
    model1.build()
    # model1.fit(samples=1)

    # check that the random effects design matrices have the same shape
    X0 = pd.concat([pd.DataFrame(t.data) if not isinstance(t.data, dict) else
                    pd.concat([pd.DataFrame(t.data[x])
                               for x in t.data.keys()], axis=1)
                    for t in model0.random_terms.values()], axis=1)
    X1 = pd.concat([pd.DataFrame(t.data) if not isinstance(t.data, dict) else
                    pd.concat([pd.DataFrame(t.data[x])
                               for x in t.data.keys()], axis=1)
                    for t in model0.random_terms.values()], axis=1)
    assert X0.shape == X1.shape

    # check that the random effect design matrix contain the same columns,
    # even if term names / columns names / order of columns is different
    X0_set = set(tuple(X0.iloc[:, i]) for i in range(len(X0.columns)))
    X1_set = set(tuple(X1.iloc[:, i]) for i in range(len(X1.columns)))
    assert X0_set == X1_set

    # check that fixed effect design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)

    # check that add_formula and add_term models have same priors for random
    # effects
    priors0 = {x.name: x.prior.args[
        'sd'].args for x in model0.terms.values() if x.random}
    priors1 = {x.name: x.prior.args[
        'sd'].args for x in model1.terms.values() if x.random}
    assert set(priors0) == set(priors1)


def test_logistic_regression(crossed_data):
    # build model using formula
    model0 = Model(crossed_data)
    model0.fit('threecats[b] ~ continuous + dummy',
               family='binomial', link='logit', run=False)
    model0.build()
    fitted = model0.fit(samples=100)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('threecats',
                 data=pd.DataFrame(1*(crossed_data['threecats'] == 'b')),
                 family='binomial', link='logit')
    model1.add_intercept()
    model1.add_term('continuous')
    model1.add_term('dummy')
    model1.build()
    model1.fit(samples=1)

    # check that term names agree
    assert set(model0.term_names) == set(model1.term_names)

    # check that design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)

    # test that summary reminds user which event is being modeled
    fitted.summary()

    # test that traceplot reminds user which event is being modeled
    fitted.plot()

def test_poisson_regression(crossed_data):
    # build model using formula
    crossed_data['count'] = (crossed_data['Y'] - crossed_data['Y'].min()).round()
    model0 = Model(crossed_data)
    model0.fit('count ~ threecats + continuous + dummy',
        family='poisson', run=False)
    model0.build()
    model0.fit(samples=1)

    # build model using add_term
    model1 = Model(crossed_data)
    model1.add_y('count', family='poisson')
    model1.add_intercept()
    model1.add_term('threecats')
    model1.add_term('continuous')
    model1.add_term('dummy')
    model1.build()
    model1.fit(samples=1)

    # check that term names agree
    assert set(model0.term_names) == set(model1.term_names)

    # check that design matries are the same,
    # even if term names / level names / order of columns is different
    X0 = set([tuple(t.data[:, lev]) for t in model0.fixed_terms.values()
              for lev in range(len(t.levels))])
    X1 = set([tuple(t.data[:, lev]) for t in model1.fixed_terms.values()
              for lev in range(len(t.levels))])
    assert X0 == X1

    # check that add_formula and add_term models have same priors for fixed
    # effects
    priors0 = {
        x.name: x.prior.args for x in model0.terms.values() if not x.random}
    priors1 = {
        x.name: x.prior.args for x in model1.terms.values() if not x.random}
    assert set(priors0) == set(priors1)
