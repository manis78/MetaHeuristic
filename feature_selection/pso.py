from __future__ import print_function
import random
from timeit import time

from deap import base
from deap import tools

from .base import _BaseMetaHeuristic
from .base import BaseMask

import operator
import math

class PSO(_BaseMetaHeuristic):
    """Implementation of a Genetic Algorithm for Feature Selection

    Parameters
    ----------
    classifier : sklearn classifier , (default=SVM)
            Any classifier that adheres to the scikit-learn API
    
    cross_over_prob :  float in [0,1], (default=0.5)
            Probability of happening a cross-over in a individual (chromosome)

    individual_mutation_probability : float in [0,1], (default=0.05)
            Probability of happening mutation in a individual ( chromosome )

    gene_mutation_prob : float in [0,1], (default=0.05)
            For each gene in the individual (chromosome) chosen for mutation,
            is the probability of it being mutate

    number_gen : positive integer, (default=10)
            Number of generations

    size_pop : positive integer, (default=40)
            Number of individuals (choromosome ) in the population

    verbose : boolean, (default=False)
            If true, print information in every generation
            
    repeat : positive int, (default=1)
            Number of times to repeat the fitting process

    make_logbook : boolean, (default=False)
            If True, a logbook from DEAP will be made
            
    parallel : boolean, (default=False)
            Set to True if you want to use multiprocessors
            
    cv_metric_fuction : callable, (default=matthews_corrcoef)            
            A metric score function as stated in the sklearn http://scikit-learn.org/stable/modules/model_evaluation.html#scoring-parameter
    
    features_metric_function : callable, (default=pow(sum(mask)/(len(mask)*5), 2))
            A function that return a float from the binary mask of features
    """

    def __init__(self, classifier=None, cross_over_prob=0.5,
                 individual_mut_prob=0.05, gene_mutation_prob=0.05,
                 number_gen=10, size_pop=40, verbose=0, repeat=1,
                 make_logbook=False, random_state=None, parallel=False,
                 cv_metric_fuction=None, features_metric_function=None):
    
        super(PSO, self).__init__(
                name = "PSO",
                classifier=classifier, 
                number_gen=number_gen,  
                verbose=verbose,
                repeat=repeat,
                parallel=parallel, 
                make_logbook=make_logbook,
                random_state=random_state,
                cv_metric_fuction=cv_metric_fuction,
                features_metric_function=features_metric_function)
        
        self.individual_mut_prob = individual_mut_prob
        self.gene_mutation_prob = gene_mutation_prob
        self.cross_over_prob = cross_over_prob
        self.size_pop = size_pop        
        
        self.toolbox = base.Toolbox()
        self.toolbox.register("attribute", self._gen_in)
        self.toolbox.register("individual", tools.initIterate,
                              BaseMask, self.toolbox.attribute, speed=list, 
                              smin=None, smax=None, best=None)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
        self.toolbox.register("map", map)
        self.toolbox.register("evaluate", self._evaluate, X= None, y=None)
        self.toolbox.register("mutate", tools.mutUniformInt, low=0, up=1,
                              indpb=self.gene_mutation_prob)

        if parallel:
            from multiprocessing import Pool
            self.toolbox.register("map", Pool().map)
        else:
            self.toolbox.register("map", map)
            
    def _gen_in(self):
        ind = super(PSO, self)._gen_in()
        ind.speed = [random.uniform(self.smin, self.smax) for _ in range(len(ind))]
        return ind
    
    def updateParticle(self, part, best, phi1, phi2):
        
        # Update Personal Best    
        if not part.best or part.best.fitness < part.fitness:
            part.best =  self.toolbox.clone(part)
        
        # Personal Influence
        u1 = (random.uniform(0, phi1) for _ in range(len(part)))
        v_u1 = map(operator.mul, u1, map(operator.sub, part.best, part))
        
        # Global Influence
        u2 = (random.uniform(0, phi2) for _ in range(len(part)))
        v_u2 = map(operator.mul, u2, map(operator.sub, best, part))
        
        # Computate Speed
        part.speed = list(map(operator.add, part.speed, 
                              map(operator.add, v_u1, v_u2)))
        
        # Verifiy speed bounds
        for i, speed in enumerate(part.speed):
            if speed < self.smin:
                part.speed[i] = self.smin
            elif speed > self.smax:
                part.speed[i] = self.smax
        
        # Update Position
        part[:] = list(map(operator.add, part, part.speed))
        
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
        
        self.set_params(**arg)
        
        X,y = self._set_dataset(X=X, y=y, normalize=normalize)
        
        self._set_fit()
        for i in range(self.repeat):
            pop = self.toolbox.population(self.size_pop)
            hof = tools.HallOfFame(1)
            pareto_front = tools.ParetoFront()
            
            # Evaluate the entire population
            fitnesses = self.toolbox.map(self.toolbox.evaluate, pop)
            for ind, fit in zip(pop, fitnesses):
                ind.fitness.values = fit

            for g in range(self.number_gen):
                # Select the next generation individuals
                offspring = self.toolbox.select(pop, len(pop))
                # Clone the selected individuals
                offspring = list(map(self.toolbox.clone, offspring))

                # Apply crossover and mutation on the offspring
                for child1, child2 in zip(offspring[::2], offspring[1::2]):
                    if random.random() < self.cross_over_prob:
                        self.toolbox.mate(child1, child2)
                        del child1.fitness.values
                        del child2.fitness.values

                for mutant in offspring:
                    if random.random() < self.individual_mut_prob:
                        self.toolbox.mutate(mutant)
                        del mutant.fitness.values

                # Evaluate the individuals with an invalid fitness ( new individuals)
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = self.toolbox.map(self.toolbox.evaluate, invalid_ind)
                for ind, fit in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit

                # The population is entirely replaced by the offspring
                pop[:] = offspring

                # Log statistic
                hof.update(pop)
                pareto_front.update(pop)
                if self.make_logbook:
                        self.logbook[i].record(gen=g,
                                               best_fit=hof[0].fitness.values[0],
                                               **self.stats.compile(pop))
                        self._make_generation( hof, pareto_front)
                        
                if self.verbose:
                    print("Repetition:", i+1 ,"Generation: ", g + 1, "/", self.number_gen,
                          "Elapsed time: ", time.clock() - initial_time, end="\r")

            self._make_repetition(hof,pareto_front)

        self.estimator.fit(X= self.transform(X), y=y)

        return self
    
    def set_params(self, **params):
        super(PSO, self).set_params(**params)

        self.toolbox.register("mutate", tools.mutUniformInt, low=0, up=1,
                                  indpb=self.gene_mutation_prob)
        if self.parallel:
            from multiprocessing import Pool
            self.toolbox.register("map", Pool().map)
        else:
            self.toolbox.register("map", map)    
            
        return self