import pytest
from bambi.models import Term, Model
from bambi.priors import Prior
from os.path import dirname, join
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')


@pytest.fixture(scope="module")
def diabetes_data():
    data_dir = join(dirname(__file__), 'data')
    data = pd.read_csv(join(data_dir, 'diabetes.txt'), sep='\t')
    data['age_grp'] = 0
    data['age_grp'][data['AGE'] > 40] = 1
    data['age_grp'][data['AGE'] > 60] = 2
    return data


@pytest.fixture(scope="module")
def base_model(diabetes_data):
    return Model(diabetes_data)


def test_term_init(diabetes_data):
    # model = Model(diabetes_data)
    # term = Term(model, 'BMI', diabetes_data['BMI'])
    term = Term('BMI', diabetes_data['BMI'])
    # Test that all defaults are properly initialized
    assert term.name == 'BMI'
    assert term.categorical == False
    assert not term.random
    assert term.levels is not None
    assert term.data.shape == (442, 1)


def test_distribute_random_effect_over(diabetes_data):
    # Random slopes
    model = Model(diabetes_data)
    model.add_term('age_grp', over='BMI', categorical=False, random=True)
    assert model.terms['age_grp|BMI'].data.shape == (442, 163)
    # Nested or crossed random intercepts
    model.reset()
    model.add_term('age_grp', over='BMI', categorical=True, random=True,
                   drop_first=False)
    t = model.terms['age_grp|BMI'].data
    assert isinstance(t, dict)
    assert t['age_grp[0]'].shape == (442, 83)


def test_model_init_from_filename():
    from os.path import dirname, join
    data_dir = join(dirname(__file__), 'data')
    filename = join(data_dir, 'diabetes.txt')
    model = Model(filename)
    assert isinstance(model.data, pd.DataFrame)
    assert model.data.shape == (442, 11)
    assert 'BMI' in model.data.columns


def test_model_init_and_intercept(diabetes_data):

    model = Model(diabetes_data, intercept=True)
    assert hasattr(model, 'data')
    assert 'Intercept' in model.terms
    assert len(model.terms) == 1
    assert model.y is None
    assert hasattr(model, 'backend')
    model = Model(diabetes_data)
    assert 'Intercept' not in model.terms
    assert not model.terms


def test_model_term_names_property(diabetes_data):
    model = Model(diabetes_data)
    model.add_term('BMI')
    model.add_term('BP')
    model.add_term('S1')
    assert model.term_names == ['BMI', 'BP', 'S1']


def test_add_term_to_model(base_model):

    base_model.add_term('BMI')
    assert isinstance(base_model.terms['BMI'], Term)
    base_model.add_term('age_grp', random=False, categorical=True)
    # Test that arguments are passed appropriately onto Term initializer
    base_model.add_term(
        'age_grp', random=True, over='BP', categorical=True)
    assert isinstance(base_model.terms['age_grp|BP'], Term)


def test_one_shot_formula_fit(base_model):
    base_model.fit('BMI ~ S1 + S2', samples=50, run=False)
    base_model.build()
    nv = base_model.backend.model.named_vars
    targets = ['BMI', 'b_S1', 'b_Intercept']
    assert len(set(nv.keys()) & set(targets)) == 3


def test_invalid_chars_in_random_effect(base_model):
    with pytest.raises(ValueError):
        base_model.fit(random=['1+BP|age_grp'])


def test_update_term_priors_after_init(diabetes_data):
    model = Model(diabetes_data)
    model.add_term('BMI')
    model.add_term('S1')
    model.add_term('age_grp', random=True, over='BP')

    p1 = Prior('Normal', mu=-10, sd=10)
    p2 = Prior('Beta', alpha=2, beta=2)

    model.set_priors({'BMI': 0.3, 'S1': p2})
    assert model.terms['S1'].prior.args['beta'] == 2
    assert model.terms['BMI'].prior == 0.3

    model.set_priors({('S1', 'BMI'): p1})
    assert model.terms['S1'].prior.args['sd'] == 10
    assert model.terms['BMI'].prior.args['mu'] == -10

    p3 = Prior('Normal', mu=0, sd=Prior('Normal', mu=0, sd=7))
    model.set_priors(fixed=0.4, random=p3)
    assert model.terms['BMI'].prior == 0.4
    assert model.terms['age_grp|BP'].prior.args['sd'].args['sd'] == 7


def test_add_formula_append(diabetes_data):
    model = Model(diabetes_data)
    model.add_y('BMI')
    model.add_formula('S1')
    assert hasattr(model, 'y') and model.y is not None and model.y.name == 'BMI'
    assert 'S1' in model.terms
    model.add_formula('S2', append=False)
    assert model.y is None
    assert 'S2' in model.terms
    assert 'S1' not in model.terms
