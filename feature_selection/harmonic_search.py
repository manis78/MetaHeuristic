from __future__ import print_function
from timeit import time
from deap import base
from deap import tools
from .base import *
from .base import _BaseMetaHeuristic
from sklearn.svm import SVC
import random
from sklearn.base import clone
from multiprocessing import Pool


class HarmonicSearch(_BaseMetaHeuristic):
    """Implementation of a Harmonic Search Algorithm for Feature Selection

    Parameters
    ----------
    HMCR : float in [0,1], (default=0.95)
            Is the Harmonic Memory Considering Rate

    number_gen : positive integer, (default=100)
            Number of generations

    size_pop : positive integer, (default=50)
            Size of the Harmonic Memory

    verbose : boolean, (default=False)
            If true, print information in every generation

    repeat : positive int, (default=1)
            Number of times to repeat the fitting process

    parallel : boolean, (default=False)
            Set to True if you want to use multiprocessors

    make_logbook : boolean, (default=False)
            If True, a logbook from DEAP will be made

    cv_metric_function : callable, (default=matthews_corrcoef)
            A metric score function as stated in the sklearn http://scikit-learn.org/stable/modules/model_evaluation.html#scoring-parameter

    features_metric_function : callable, (default=pow(sum(mask)/(len(mask)*5), 2))
            A function that return a float from the binary mask of features
    """
    def __init__(self, estimator=None, HMCR=0.95, sorting_method='simple',
                 number_gen=100, size_pop=50, verbose=0, repeat=1,
                 make_logbook=False, random_state=None, parallel=False,
                 cv_metric_function=None, features_metric_function=None,
                 print_fnc=None, skip=0, name="HarmonicSearch"):

        self.name = name
        self.estimator = estimator
        self.number_gen = number_gen
        self.verbose = verbose
        self.repeat = repeat
        self.parallel = parallel
        self.make_logbook = make_logbook
        self.random_state = random_state
        self.cv_metric_function = cv_metric_function
        self.features_metric_function = features_metric_function
        self.print_fnc = print_fnc
        self.HMCR = HMCR
        self.size_pop = size_pop
        self.skip = skip
        self.sorting_method = sorting_method
        random.seed(self.random_state)

    def _setup(self):
        super()._setup()

        self._toolbox.register("attribute", self._gen_in)

        self._toolbox.register("individual", tools.initIterate,
                               BaseMask, self._toolbox.attribute)

        self._toolbox.register("population", tools.initRepeat,
                               list, self._toolbox.individual)

        if(self.sorting_method == 'simple'):
            self._toolbox.register( "sort", sorted, key=lambda ind: ind.fitness.values[0])
        elif(self.sorting_method == 'NSGA2'):
            self._toolbox.register( "sort", tools.selNSGA2, k=self.size_pop+1)
        elif(self.sorting_method == 'NSGA3'):
            self._toolbox.register( "sort", tools.selNSGA3, k=self.size_pop+1)
        else:
            raise ValueError("The {} sorting method is not valid".format(self.sorting_method))

        self._toolbox.register("evaluate", self._evaluate, X=None, y=None)

        if( self.HMCR < 0 or self.HMCR > 1):
            raise ValueError("The HMCR param is {}, but should be in the interval [0,1]".format(self.HMCR))
        
        self._toolbox.register("mutate", tools.mutFlipBit, indpb=1-self.HMCR)

    def fit(self, X=None, y=None, normalize=False, **arg):
        """ Fit method

        Parameters
        ----------
        X : array of shape [n_samples, n_features]
                The input samples

        y : array of shape [n_samples, 1]
                The input of labels

        normalize : boolean, (default=False)
                If true, StandardScaler will be applied to X

        **arg : parameters
                Set parameters
        """
        initial_time = time.clock()

        self._setup()

        self.set_params(**arg)

        X, y = self._set_dataset(X=X, y=y, normalize=normalize)

        for i in range(self.repeat):
            harmony_mem = self._toolbox.population(n=self.size_pop)
            hof = tools.HallOfFame(1)
            pareto_front = tools.ParetoFront()

            # Evaluate the entire population
            fitnesses = self._toolbox.map(self._toolbox.evaluate, harmony_mem)

            for ind, fit in zip(harmony_mem, fitnesses):
                ind.fitness.values = fit

            for g in range(self.number_gen):

                # Improvise a New Harmony
                new_harmony = self._improvise(harmony_mem)
                new_harmony.fitness.values = self._toolbox.evaluate(new_harmony)
                harmony_mem.append(new_harmony)

                # Remove the Worst Harmony
                harmony_mem = self._toolbox.sort(harmony_mem)
                harmony_mem.pop()

                # Log statistic
                hof.update(harmony_mem)
                pareto_front.update(harmony_mem)

                if self.skip == 0 or g % self.skip == 0:
                    if self.make_logbook:
                        self.logbook[i].record(gen=g,
                                               best_fit=hof[0].fitness.values[0],
                                               **self.stats.compile(harmony_mem))
                        self._make_generation_log(hof, pareto_front)

                    if self.verbose:
                        self._print(g, i, initial_time, time.clock())

            self._make_repetition_log(hof, pareto_front)

        self._estimator.fit(X=self.transform(X), y=y)

        return self

    def _improvise(self, pop):
        """ Function that improvise a new harmony"""
        # HMCR = Harmonic Memory Considering Rate
        # pylint: disable=E1101
        new_harmony = self._toolbox.individual()

        rand_list = self._random_object.randint(low=0, high=len(pop),
                                                size=len(new_harmony))

        for i in range(len(new_harmony)):
            new_harmony[i] = pop[rand_list[i]][i]

        self._toolbox.mutate(new_harmony)

        return new_harmony
