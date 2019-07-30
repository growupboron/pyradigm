"""

Base module to define the ABCs for all MLDatasets

"""

import copy
import os
import pickle
import random
import warnings
from collections import Counter, OrderedDict, Sequence
from itertools import islice
from os.path import isfile, realpath
from sys import version_info
import numpy as np

from abc import ABC, abstractmethod

class BaseDataset(ABC):
    """Abstract Base class MLDataset.

    self.__class__() refers to the inherited child class at runtime!

    """


    def __init__(self, filepath=None,
                 in_dataset=None,
                 arff_path=None,
                 data=None, targets=None, classes=None,
                 description='',
                 feature_names=None,
                 encode_nonnumeric=False):
        """
        Default constructor.
        Recommended way to construct the dataset is via add_sample method, one samplet
        at a time, as it allows for unambiguous identification of each row in data matrix.

        This constructor can be used in 3 ways:
            - As a copy constructor to make a copy of the given in_dataset
            - Or by specifying the tuple of data, targets and classes.
                In this usage, you can provide additional inputs such as description
                and feature_names.
            - Or by specifying a file path which contains previously saved MLDataset.

        Parameters
        ----------
        filepath : str
            path to saved MLDataset on disk, to directly load it.

        in_dataset : MLDataset
            MLDataset to be copied to create a new one.

        arff_path : str
            Path to a dataset saved in Weka's ARFF file format.

        data : dict
            dict of features (keys are treated to be samplet ids)

        targets : dict
            dict of targets
            (keys must match with data/classes, are treated to be samplet ids)

        classes : dict
            dict of class names
            (keys must match with data/targets, are treated to be samplet ids)

        description : str
            Arbitrary string to describe the current dataset.

        feature_names : list, ndarray
            List of names for each feature in the dataset.

        encode_nonnumeric : bool
            Flag to specify whether to encode non-numeric features (categorical,
            nominal or string) features to numeric values.
            Currently used only when importing ARFF files.
            It is usually better to encode your data at the source,
            and them import them to Use with caution!

        Raises
        ------
        ValueError
            If in_dataset is not of type MLDataset or is empty, or
            An invalid combination of input args is given.
        IOError
            If filepath provided does not exist.

        """

        if filepath is not None:
            if isfile(realpath(filepath)):
                # print('Loading the dataset from: {}'.format(filepath))
                self.__load(filepath)
            else:
                raise IOError('Specified file could not be read.')
        elif arff_path is not None:
            arff_path = realpath(arff_path)
            if isfile(arff_path):
                self.__load_arff(arff_path, encode_nonnumeric)
            else:
                raise IOError('Given ARFF can not be found!')
        elif in_dataset is not None:
            if not isinstance(in_dataset, self.__class__):
                raise ValueError('Invalid class input: {} expected!'
                                 ''.format(self.__class__))
            if in_dataset.num_samples <= 0:
                raise ValueError('Dataset to copy is empty.')
            self.__copy(in_dataset)
        elif data is None and targets is None and classes is None:
            # TODO refactor the code to use only basic dict,
            # as it allows for better equality comparisons
            self.__data = OrderedDict()
            self.__targets = OrderedDict()
            self.__classes = OrderedDict()
            self.__num_features = 0
            self.__dtype = None
            self.__description = ''
            self.__feature_names = None
        elif data is not None and targets is not None and classes is not None:
            # ensuring the inputs really correspond to each other
            # but only in data, targets and classes, not feature names
            self.__validate(data, targets, classes)

            # OrderedDict to ensure the order is maintained when
            # data/targets are returned in a matrix/array form
            self.__data = OrderedDict(data)
            self.__targets = OrderedDict(targets)
            self.__classes = OrderedDict(classes)
            self.__description = description

            sample_ids = list(data)
            features0 = data[sample_ids[0]]
            self.__num_features = features0.size if isinstance(features0,
                                                               np.ndarray) else len(
                features0)
            self.__dtype = type(data[sample_ids[0]])

            # assigning default names for each feature
            if feature_names is None:
                self.__feature_names = self.__str_names(self.num_features)
            else:
                self.__feature_names = feature_names

        else:
            raise ValueError('Incorrect way to construct the dataset.')


    @property
    def data(self):
        """data in its original dict form."""
        return self.__data


    def data_and_targets(self):
        """
        Dataset features and targets in a matrix form for learning.

        Also returns sample_ids in the same order.

        Returns
        -------
        data_matrix : ndarray
            2D array of shape [num_samples, num_features]
            with features corresponding row-wise to sample_ids
        targets : ndarray
            Array of numeric targets for each samplet corresponding row-wise to sample_ids
        sample_ids : list
            List of samplet ids

        """

        sample_ids = np.array(self.keys)
        label_dict = self.targets
        matrix = np.full([self.num_samples, self.num_features], np.nan)
        targets = np.full([self.num_samples, 1], np.nan)
        for ix, samplet in enumerate(sample_ids):
            matrix[ix, :] = self.__data[samplet]
            targets[ix] = label_dict[samplet]

        return matrix, np.ravel(targets), sample_ids


    @data.setter
    def data(self, values, feature_names=None):
        """
        Populates this dataset with the provided data.
        Usage of this method is discourage (unless you know what you are doing).

        Parameters
        ----------
        values : dict
            dict of features keyed in by samplet ids.

        feature_names : list of str
            New feature names for the new features, if available.

        Raises
        ------
        ValueError
            If number of samplets does not match the size of existing set, or
            If atleast one samplet is not provided.

        """
        if isinstance(values, dict):
            if self.__targets is not None and len(self.__targets) != len(values):
                raise ValueError(
                    'number of samplets do not match the previously assigned targets')
            elif len(values) < 1:
                raise ValueError('There must be at least 1 samplet in the dataset!')
            else:
                self.__data = values
                # update dimensionality
                # assuming all keys in dict have same len arrays
                self.__num_features = len(values[self.keys[0]])

            if feature_names is None:
                self.__feature_names = self.__str_names(self.num_features)
            else:
                self.feature_names = feature_names
        else:
            raise ValueError('data input must be a dictionary!')


    @property
    def targets(self):
        """Returns the array of targets for all the samplets."""
        # TODO numeric label need to be removed,
        # as this can be made up on the fly as needed from str to num encoders.
        return self.__targets


    @targets.setter
    def targets(self, values):
        """Class targets (such as 1, 2, -1, 'A', 'B' etc.) for each samplet in the dataset."""
        if isinstance(values, dict):
            if self.__data is not None and len(self.__data) != len(values):
                raise ValueError(
                    'number of samplets do not match the previously assigned data')
            elif set(self.keys) != set(list(values)):
                raise ValueError('samplet ids do not match the previously assigned ids.')
            else:
                self.__targets = values
        else:
            raise ValueError('targets input must be a dictionary!')


    @property
    def classes(self):
        """
        Identifiers (samplet IDs, or samplet names etc)
            forming the basis of dict-type MLDataset.
        """
        return self.__classes


    @classes.setter
    def classes(self, values):
        """Classes setter."""
        if isinstance(values, dict):
            if self.__data is not None and len(self.__data) != len(values):
                raise ValueError(
                    'number of samplets do not match the previously assigned data')
            elif set(self.keys) != set(list(values)):
                raise ValueError('samplet ids do not match the previously assigned ids.')
            else:
                self.__classes = values
        else:
            raise ValueError('classes input must be a dictionary!')


    @property
    def feature_names(self):
        "Returns the feature names as an numpy array of strings."

        return self.__feature_names


    @feature_names.setter
    def feature_names(self, names):
        "Stores the text targets for features"

        if len(names) != self.num_features:
            raise ValueError("Number of names do not match the number of features!")
        if not isinstance(names, (Sequence, np.ndarray, np.generic)):
            raise ValueError("Input is not a sequence. "
                             "Ensure names are in the same order "
                             "and length as features.")

        self.__feature_names = np.array(names)


    @property
    def class_sizes(self):
        """Returns the sizes of different objects in a Counter object."""
        return Counter(self.classes.values())


    @staticmethod
    def __take(nitems, iterable):
        """Return first n items of the iterable as a list"""
        return dict(islice(iterable, int(nitems)))


    @staticmethod
    def __str_names(num):

        return np.array(['f{}'.format(x) for x in range(num)])


    def glance(self, nitems=5):
        """Quick and partial glance of the data matrix.

        Parameters
        ----------
        nitems : int
            Number of items to glance from the dataset.
            Default : 5

        Returns
        -------
        dict

        """
        nitems = max([1, min([nitems, self.num_samples - 1])])
        return self.__take(nitems, iter(self.__data.items()))


    def summarize_classes(self):
        """
        Summary of classes: names, numeric targets and sizes

        Returns
        -------
        tuple : class_set, label_set, class_sizes

        class_set : list
            List of names of all the classes
        label_set : list
            Label for each class in class_set
        class_sizes : list
            Size of each class (number of samplets)

        """

        class_sizes = np.zeros(len(self.class_set))
        for idx, cls in enumerate(self.class_set):
            class_sizes[idx] = self.class_sizes[cls]

        # TODO consider returning numeric label set e.g. for use in scikit-learn
        return self.class_set, self.label_set, class_sizes


    @classmethod
    def check_features(self, features):
        """
        Method to ensure data to be added is not empty and vectorized.

        Parameters
        ----------
        features : iterable
            Any data that can be converted to a numpy array.

        Returns
        -------
        features : numpy array
            Flattened non-empty numpy array.

        Raises
        ------
        ValueError
            If input data is empty.
        """

        if not isinstance(features, np.ndarray):
            features = np.asarray(features)

        if features.size <= 0:
            raise ValueError('provided features are empty.')

        if features.ndim > 1:
            features = np.ravel(features)

        return features


    # TODO try implementing based on pandas
    def add_sample(self, sample_id, features, target,
                   class_id=None,
                   overwrite=False,
                   feature_names=None):
        """Adds a new samplet to the dataset with its features, label and class ID.

        This is the preferred way to construct the dataset.

        Parameters
        ----------

        sample_id : str, int
            The identifier that uniquely identifies this samplet.
        features : list, ndarray
            The features for this samplet
        label : int, str
            The label for this samplet
        class_id : int, str
            The class for this samplet.
            If not provided, label converted to a string becomes its ID.
        overwrite : bool
            If True, allows the overwite of features for an existing subject ID.
            Default : False.
        feature_names : list
            The names for each feature. Assumed to be in the same order as `features`

        Raises
        ------
        ValueError
            If `sample_id` is already in the MLDataset (and overwrite=False), or
            If dimensionality of the current samplet does not match the current, or
            If `feature_names` do not match existing names
        TypeError
            If samplet to be added is of different data type compared to existing samplets.

        """

        if sample_id in self.__data and not overwrite:
            raise ValueError('{} already exists in this dataset!'.format(sample_id))

        # ensuring there is always a class name, even when not provided by the user.
        # this is needed, in order for __str__ method to work.
        # TODO consider enforcing label to be numeric and class_id to be string
        #  so portability with other packages is more uniform e.g. for use in scikit-learn
        if class_id is None:
            class_id = str(target)

        features = self.check_features(features)
        if self.num_samples <= 0:
            self.__data[sample_id] = features
            self.__targets[sample_id] = target
            self.__classes[sample_id] = class_id
            self.__dtype = type(features)
            self.__num_features = features.size if isinstance(features,
                                                              np.ndarray) else len(
                features)
            if feature_names is None:
                self.__feature_names = self.__str_names(self.num_features)
        else:
            if self.__num_features != features.size:
                raise ValueError('dimensionality of this samplet ({}) '
                                 'does not match existing samplets ({})'
                                 ''.format(features.size, self.__num_features))
            if not isinstance(features, self.__dtype):
                raise TypeError("Mismatched dtype. Provide {}".format(self.__dtype))

            self.__data[sample_id] = features
            self.__targets[sample_id] = target
            self.__classes[sample_id] = class_id
            if feature_names is not None:
                # if it was never set, allow it
                # class gets here when adding the first samplet,
                #   after dataset was initialized with empty constructor
                if self.__feature_names is None:
                    self.__feature_names = np.array(feature_names)
                else:  # if set already, ensure a match
                    if not np.array_equal(self.feature_names, np.array(feature_names)):
                        raise ValueError(
                            "supplied feature names do not match the existing names!")


    def del_sample(self, sample_id):
        """
        Method to remove a samplet from the dataset.

        Parameters
        ----------
        sample_id : str
            samplet id to be removed.

        Raises
        ------
        UserWarning
            If samplet id to delete was not found in the dataset.

        """
        if sample_id not in self.__data:
            warnings.warn('Sample to delete not found in the dataset - nothing to do.')
        else:
            self.__data.pop(sample_id)
            self.__classes.pop(sample_id)
            self.__targets.pop(sample_id)
            print('{} removed.'.format(sample_id))


    def get_feature_subset(self, subset_idx):
        """
        Returns the subset of features indexed numerically.

        Parameters
        ----------
        subset_idx : list, ndarray
            List of indices to features to be returned

        Returns
        -------
        MLDataset : MLDataset
            with subset of features requested.

        Raises
        ------
        UnboundLocalError
            If input indices are out of bounds for the dataset.

        """

        subset_idx = np.asarray(subset_idx)
        if not (max(subset_idx) < self.__num_features) and (min(subset_idx) >= 0):
            raise UnboundLocalError('indices out of range for the dataset. '
                                    'Max index: {} Min index : 0'.format(
                self.__num_features))

        sub_data = {samplet: features[subset_idx] for samplet, features in
                    self.__data.items()}
        new_descr = 'Subset features derived from: \n ' + self.__description
        subdataset = self.__class__(data=sub_data, targets=self.__targets,
                                    classes=self.__classes, description=new_descr,
                                    feature_names=self.__feature_names[subset_idx])

        return subdataset


    @staticmethod
    def keys_with_value(dictionary, value):
        "Returns a subset of keys from the dict with the value supplied."

        subset = [key for key in dictionary if dictionary[key] == value]

        return subset



    def transform(self, func, func_description=None):
        """
        Applies a given a function to the features of each subject
            and returns a new dataset with other info unchanged.

        Parameters
        ----------
        func : callable
            A valid callable that takes in a single ndarray and returns a single ndarray.
            Ensure the transformed dimensionality must be the same for all subjects.

            If your function requires more than one argument,
            use `functools.partial` to freeze all the arguments
            except the features for the subject.

        func_description : str, optional
            Human readable description of the given function.

        Returns
        -------
        xfm_ds : MLDataset
            with features obtained from subject-wise transform

        Raises
        ------
        TypeError
            If given func is not a callable
        ValueError
            If transformation of any of the subjects features raises an exception.

        Examples
        --------
        Simple:

        .. code-block:: python

            from pyradigm import MLDataset

            thickness = MLDataset(in_path='ADNI_thickness.csv')
            pcg_thickness = thickness.apply_xfm(func=get_pcg, description = 'applying ROI mask for PCG')
            pcg_median = pcg_thickness.apply_xfm(func=np.median, description='median per subject')


        Complex example with function taking more than one argument:

        .. code-block:: python

            from pyradigm import MLDataset
            from functools import partial
            import hiwenet

            thickness = MLDataset(in_path='ADNI_thickness.csv')
            roi_membership = read_roi_membership()
            hw = partial(hiwenet, groups = roi_membership)

            thickness_hiwenet = thickness.transform(func=hw, description = 'histogram weighted networks')
            median_thk_hiwenet = thickness_hiwenet.transform(func=np.median, description='median per subject')

        """

        if not callable(func):
            raise TypeError('Given function {} is not a callable'.format(func))

        xfm_ds = self.__class__()
        for samplet, data in self.__data.items():
            try:
                xfm_data = func(data)
            except:
                print('Unable to transform features for {}. Quitting.'.format(samplet))
                raise

            xfm_ds.add_sample(samplet, xfm_data,
                              target=self.__targets[samplet],
                              class_id=self.__classes[samplet])

        xfm_ds.description = "{}\n{}".format(func_description, self.__description)

        return xfm_ds


    def train_test_split_ids(self, train_perc=None, count_per_class=None):
        """
        Returns two disjoint sets of samplet ids for use in cross-validation.

        Offers two ways to specify the sizes: fraction or count.
        Only one access method can be used at a time.

        Parameters
        ----------
        train_perc : float
            fraction of samplets from each class to build the training subset.

        count_per_class : int
            exact count of samplets from each class to build the training subset.

        Returns
        -------
        train_set : list
            List of ids in the training set.
        test_set : list
            List of ids in the test set.

        Raises
        ------
        ValueError
            If the fraction is outside open interval (0, 1), or
            If counts are outside larger than the smallest class, or
            If unrecongized format is provided for input args, or
            If the selection results in empty subsets for either train or test sets.

        """

        _ignore1, _ignore2, class_sizes = self.summarize_classes()
        smallest_class_size = np.min(class_sizes)

        if count_per_class is None and (0.0 < train_perc < 1.0):
            if train_perc < 1.0 / smallest_class_size:
                raise ValueError('Training percentage selected too low '
                                 'to return even one samplet from the smallest class!')
            train_set = self.random_subset_ids(perc_per_class=train_perc)
        elif train_perc is None and count_per_class > 0:
            if count_per_class >= smallest_class_size:
                raise ValueError(
                    'Selections would exclude the smallest class from test set. '
                    'Reduce samplet count per class for the training set!')
            train_set = self.random_subset_ids_by_count(count_per_class=count_per_class)
        else:
            raise ValueError('Invalid or out of range selection: '
                             'only one of count or percentage can be used to select subset.')

        test_set = list(set(self.keys) - set(train_set))

        if len(train_set) < 1 or len(test_set) < 1:
            raise ValueError('Selection resulted in empty training or test set: '
                             'check your selections or dataset!')

        return train_set, test_set



    @abstractmethod
    def random_subset(self, perc=0.5):
        """
        Returns a random sub-dataset of specified size by percentage

        Parameters
        ----------
        perc : float
            Fraction of samplets to be taken
            The meaning of this varies based on the child class: for
            classification- oriented MLDataset, this can be perc from each class.

        Returns
        -------
        subdataset : MLDataset
            random sub-dataset of specified size.

        """



    def get_subset(self, subset_ids):
        """
        Returns a smaller dataset identified by their keys/samplet IDs.

        Parameters
        ----------
        subset_ids : list
            List od samplet IDs to extracted from the dataset.

        Returns
        -------
        sub-dataset : MLDataset
            sub-dataset containing only requested samplet IDs.

        """

        num_existing_keys = sum([1 for key in subset_ids if key in self.__data])
        if subset_ids is not None and num_existing_keys > 0:
            # ensure items are added to data, targets etc in the same order of samplet IDs
            # TODO come up with a way to do this even when not using OrderedDict()
            # putting the access of data, targets and classes in the same loop  would
            # ensure there is correspondence across the three attributes of the class
            data = self.__get_subset_from_dict(self.__data, subset_ids)
            targets = self.__get_subset_from_dict(self.__targets, subset_ids)
            if self.__classes is not None:
                classes = self.__get_subset_from_dict(self.__classes, subset_ids)
            else:
                classes = None
            subdataset = self.__class__(data=data, targets=targets, classes=classes)
            # Appending the history
            subdataset.description += '\n Subset derived from: ' + self.description
            subdataset.feature_names = self.__feature_names
            subdataset.__dtype = self.dtype
            return subdataset
        else:
            warnings.warn('subset of IDs requested do not exist in the dataset!')
            return self.__class__()


    def get_data_matrix_in_order(self, subset_ids):
        """
        Returns a numpy array of features, rows in the same order as subset_ids

        Parameters
        ----------
        subset_ids : list
            List od samplet IDs to extracted from the dataset.

        Returns
        -------
        matrix : ndarray
            Matrix of features, for each id in subset_ids, in order.
        """

        if len(subset_ids) < 1:
            warnings.warn('subset must have atleast one ID - returning empty matrix!')
            return np.empty((0, 0))

        if isinstance(subset_ids, set):
            raise TypeError('Input set is not ordered, hence can not guarantee order! '
                            'Must provide a list or tuple.')

        if isinstance(subset_ids, str):
            subset_ids = [subset_ids, ]

        num_existing_keys = sum([1 for key in subset_ids if key in self.__data])
        if num_existing_keys < len(subset_ids):
            raise ValueError('One or more IDs from  subset do not exist in the dataset!')

        matrix = np.full((num_existing_keys, self.num_features), np.nan)
        for idx, sid in enumerate(subset_ids):
            matrix[idx, :] = self.__data[sid]

        return matrix


    def __contains__(self, item):
        "Boolean test of membership of a samplet in the dataset."
        if item in self.keys:
            return True
        else:
            return False


    def get(self, item, not_found_value=None):
        "Method like dict.get() which can return specified value if key not found"

        if item in self.keys:
            return self.__data[item]
        else:
            return not_found_value


    def __getitem__(self, item):
        "Method to ease data retrieval i.e. turn dataset.data['id'] into dataset['id'] "

        if item in self.keys:
            return self.__data[item]
        else:
            raise KeyError('{} not found in dataset.'.format(item))


    def __setitem__(self, item, features):
        """Method to replace features for existing samplet"""

        if item in self.__data:
            features = self.check_features(features)
            if self.__num_features != features.size:
                raise ValueError('dimensionality of supplied features ({}) '
                                 'does not match existing samplets ({})'
                                 ''.format(features.size, self.__num_features))
            self.__data[item] = features
        else:
            raise KeyError('{} not found in dataset.'
                           ' Can not replace features of a non-existing samplet.'
                           ' Add it first via .add_sample()'.format(item))

    def __iter__(self):
        "Iterator over samplets"

        for subject, data in self.data.items():
            yield subject, data


    @staticmethod
    def __get_subset_from_dict(input_dict, subset):
        # Using OrderedDict helps ensure data are added to data, targets etc
        # in the same order of samplet IDs
        return OrderedDict(
                (sid, value) for sid, value in input_dict.items() if sid in subset)


    @property
    def keys(self):
        """Sample identifiers (strings) - the basis of MLDataset (same as sample_ids)"""
        return list(self.__data)


    @property
    def sample_ids(self):
        """Sample identifiers (strings) forming the basis of MLDataset (same as keys)."""
        return self.keys


    @property
    def description(self):
        """Text description (header) that can be set by user."""
        return self.__description


    @description.setter
    def description(self, str_val):
        """Text description that can be set by user."""
        if not str_val: raise ValueError('description can not be empty')
        self.__description = str_val


    @property
    def num_features(self):
        """number of features in each samplet."""
        return np.int64(self.__num_features)


    @num_features.setter
    def num_features(self, int_val):
        "Method that should not exist!"
        raise AttributeError("num_features property can't be set, only retrieved!")


    @property
    def dtype(self):
        """number of features in each samplet."""
        return self.__dtype


    @dtype.setter
    def dtype(self, type_val):
        if self.__dtype is None:
            if not isinstance(type_val, type):
                raise TypeError('Invalid data type.')
            self.__dtype = type_val
        else:
            warnings.warn('Data type is already inferred. Can not be set!')


    @property
    def num_samples(self):
        """number of samplets in the entire dataset."""
        if self.__data is not None:
            return len(self.__data)
        else:
            return 0


    @property
    def shape(self):
        """Returns the pythonic shape of the dataset: num_samples x num_features.
        """

        return (self.num_samples, self.num_features)




    def __len__(self):
        return self.num_samples


    def __nonzero__(self):
        if self.num_samples < 1:
            return False
        else:
            return True


    def __str__(self):
        """Returns a concise and useful text summary of the dataset."""
        full_descr = list()
        if self.description not in [None, '']:
            full_descr.append(self.description)
        if bool(self):
            full_descr.append('{} samplets, {} classes, {} features'.format(
                    self.num_samples, self.num_classes, self.num_features))
            class_ids = list(self.class_sizes)
            max_width = max([len(cls) for cls in class_ids])
            num_digit = max([len(str(val)) for val in self.class_sizes.values()])
            for cls in class_ids:
                full_descr.append(
                    'Class {cls:>{clswidth}} : '
                    '{size:>{numwidth}} samplets'.format(cls=cls, clswidth=max_width,
                                                        size=self.class_sizes.get(cls),
                                                        numwidth=num_digit))
        else:
            full_descr.append('Empty dataset.')

        return '\n'.join(full_descr)


    def __format__(self, fmt_str='s'):
        if fmt_str.lower() in ['', 's', 'short']:
            return '{} samplets x {} features each in {} classes'.format(
                    self.num_samples, self.num_features, self.num_classes)
        elif fmt_str.lower() in ['f', 'full']:
            return self.__str__()
        else:
            raise NotImplementedError("Requsted type of format not implemented.\n"
                                      "It can only be 'short' (default) or 'full', "
                                      "or a shorthand: 's' or 'f' ")


    def __repr__(self):
        return self.__str__()


    @staticmethod
    def __dir__():
        """Returns the preferred list of attributes to be used with the dataset."""
        return ['add_sample',
                'glance',
                'summarize_classes',
                'sample_ids_in_class',
                'train_test_split_ids',
                'random_subset_ids',
                'random_subset_ids_by_count',
                'classes',
                'class_set',
                'class_sizes',
                'data_and_targets',
                'get_data_matrix_in_order',
                'data',
                'del_sample',
                'description',
                'extend',
                'feature_names',
                'get',
                'get_class',
                'get_subset',
                'random_subset',
                'get_feature_subset',
                'keys',
                'targets',
                'label_set',
                'num_classes',
                'num_features',
                'num_samples',
                'sample_ids',
                'save',
                'compatible',
                'transform',
                'add_classes']


    def __copy(self, other):
        """Copy constructor."""
        self.__data = copy.deepcopy(other.data)
        self.__classes = copy.deepcopy(other.classes)
        self.__targets = copy.deepcopy(other.targets)
        self.__dtype = copy.deepcopy(other.dtype)
        self.__description = copy.deepcopy(other.description)
        self.__feature_names = copy.deepcopy(other.feature_names)
        self.__num_features = copy.deepcopy(other.num_features)

        return self


    def __load(self, path):
        """Method to load the serialized dataset from disk."""
        try:
            path = os.path.abspath(path)
            with open(path, 'rb') as df:
                # loaded_dataset = pickle.load(df)
                self.__data, self.__classes, self.__targets, \
                self.__dtype, self.__description, \
                self.__num_features, self.__feature_names = pickle.load(df)

            # ensure the loaded dataset is valid
            self.__validate(self.__data, self.__classes, self.__targets)

        except IOError as ioe:
            raise IOError('Unable to read the dataset from file: {}', format(ioe))
        except:
            raise


    def __load_arff(self, arff_path, encode_nonnumeric=False):
        """Loads a given dataset saved in Weka's ARFF format. """
        try:
            from scipy.io.arff import loadarff
            arff_data, arff_meta = loadarff(arff_path)
        except:
            raise ValueError('Error loading the ARFF dataset!')

        attr_names = arff_meta.names()[:-1]  # last column is class
        attr_types = arff_meta.types()[:-1]
        if not encode_nonnumeric:
            # ensure all the attributes are numeric
            uniq_types = set(attr_types)
            if 'numeric' not in uniq_types:
                raise ValueError(
                    'Currently only numeric attributes in ARFF are supported!')

            non_numeric = uniq_types.difference({'numeric'})
            if len(non_numeric) > 0:
                raise ValueError('Non-numeric features provided ({}), '
                                 'without requesting encoding to numeric. '
                                 'Try setting encode_nonnumeric=True '
                                 'or encode features to numeric!'.format(non_numeric))
        else:
            raise NotImplementedError(
                'encoding non-numeric features to numeric is not implemented yet! '
                'Encode features beforing to ARFF.')

        self.__description = arff_meta.name  # to enable it as a label e.g. in neuropredict

        # initializing the key containers, before calling self.add_sample
        self.__data = OrderedDict()
        self.__targets = OrderedDict()
        self.__classes = OrderedDict()

        num_samples = len(arff_data)
        num_digits = len(str(num_samples))
        make_id = lambda index: 'row{index:0{nd}d}'.format(index=index, nd=num_digits)
        sample_classes = [cls.decode('utf-8') for cls in arff_data['class']]
        class_set = set(sample_classes)
        label_dict = dict()
        # encoding class names to targets 1 to n
        for ix, cls in enumerate(class_set):
            label_dict[cls] = ix + 1

        for index in range(num_samples):
            samplet = arff_data.take([index])[0].tolist()
            sample_attrs = samplet[:-1]
            sample_class = samplet[-1].decode('utf-8')
            self.add_sample(sample_id=make_id(index),  # ARFF rows do not have an ID
                            features=sample_attrs,
                            target=label_dict[sample_class],
                            class_id=sample_class)
            # not necessary to set feature_names=attr_names for each samplet,
            # as we do it globally after loop

        self.__feature_names = attr_names

        return


    def save(self, file_path):
        """
        Method to save the dataset to disk.

        Parameters
        ----------
        file_path : str
            File path to save the current dataset to

        Raises
        ------
        IOError
            If saving to disk is not successful.

        """

        # TODO need a file format that is flexible and efficient to allow the following:
        #   1) being able to read just meta info without having to load the ENTIRE dataset
        #       i.e. use case: compatibility check with #subjects, ids and their classes
        #   2) random access layout: being able to read features for a single subject!

        try:
            file_path = os.path.abspath(file_path)
            with open(file_path, 'wb') as df:
                # pickle.dump(self, df)
                pickle.dump((self.__data, self.__classes, self.__targets,
                             self.__dtype, self.__description, self.__num_features,
                             self.__feature_names),
                            df)
            return
        except IOError as ioe:
            raise IOError('Unable to save the dataset to file: {}', format(ioe))
        except:
            raise


    @staticmethod
    def __validate(data, classes, targets):
        "Validator of inputs."

        if not isinstance(data, dict):
            raise TypeError(
                'data must be a dict! keys: samplet ID or any unique identifier')
        if not isinstance(targets, dict):
            raise TypeError(
                'targets must be a dict! keys: samplet ID or any unique identifier')
        if classes is not None:
            if not isinstance(classes, dict):
                raise TypeError(
                    'targets must be a dict! keys: samplet ID or any unique identifier')

        if not len(data) == len(targets) == len(classes):
            raise ValueError('Lengths of data, targets and classes do not match!')
        if not set(list(data)) == set(list(targets)) == set(list(classes)):
            raise ValueError(
                'data, classes and targets dictionaries must have the same keys!')

        num_features_in_elements = np.unique([samplet.size for samplet in data.values()])
        if len(num_features_in_elements) > 1:
            raise ValueError(
                'different samplets have different number of features - invalid!')

        return True


    def extend(self, other):
        """
        Method to extend the dataset vertically (add samplets from  anotehr dataset).

        Parameters
        ----------
        other : MLDataset
            second dataset to be combined with the current
            (different samplets, but same dimensionality)

        Raises
        ------
        TypeError
            if input is not an MLDataset.
        """

        if not isinstance(other, self.__class__):
            raise TypeError('Incorrect type of dataset provided!')
        # assert self.__dtype==other.dtype, TypeError('Incorrect data type of features!')
        for samplet in other.keys:
            self.add_sample(samplet, other.data[samplet], other.targets[samplet],
                            other.classes[samplet])

        # TODO need a mechanism add one feature at a time, and
        #   consequently update feature names for any subset of features


    def __add__(self, other):
        "Method to combine to MLDatasets, samplet-wise or feature-wise."

        if not isinstance(other, self.__class__):
            raise TypeError('Incorrect type of dataset provided!')

        if set(self.keys) == set(other.keys):
            print('Identical keys found. '
                  'Trying to horizontally concatenate features for each samplet.')
            if not self.__classes == other.classes:
                raise ValueError(
                    'Class identifiers per samplet differ in the two datasets!')
            if other.num_features < 1:
                raise ValueError('No features to concatenate.')
            # making an empty dataset
            combined = self.__class__()
            # populating it with the concatenated feature set
            for samplet in self.keys:
                comb_data = np.concatenate([self.__data[samplet], other.data[samplet]])
                combined.add_sample(samplet, comb_data,
                                    self.__targets[samplet], self.__classes[samplet])

            comb_names = np.concatenate([self.__feature_names, other.feature_names])
            combined.feature_names = comb_names

            return combined

        elif len(set(self.keys).intersection(
                other.keys)) < 1 and self.__num_features == other.num_features:
            # making a copy of self first
            combined = self.__class__(in_dataset=self)
            # adding the new dataset
            combined.extend(other)
            return combined
        else:
            raise ArithmeticError('Two datasets could not be combined.')


    def __sub__(self, other):
        """Removing one dataset from another."""
        if not isinstance(other, type(self)):
            raise TypeError('Incorrect type of dataset provided!')

        num_existing_keys = len(set(self.keys).intersection(other.keys))
        if num_existing_keys < 1:
            warnings.warn('None of the samplet ids to be removed found in this dataset '
                          '- nothing to do.')
        if len(self.keys) == num_existing_keys:
            warnings.warn(
                'Requested removal of all the samplets - output dataset would be empty.')

        removed = copy.deepcopy(self)
        for samplet in other.keys:
            removed.del_sample(samplet)

        return removed


    def __iadd__(self, other):
        """Augmented assignment for add."""
        return self.__add__(other)


    def __isub__(self, other):
        """Augmented assignment for samplet."""
        return self.__sub__(other)


    def __eq__(self, other):
        """Equality of two datasets in samplets and their values."""
        if set(self.keys) != set(other.keys):
            print('differing samplet ids.')
            return False
        elif dict(self.__classes) != dict(other.classes):
            print('differing classes for the samplet ids.')
            return False
        elif id(self.__data) != id(other.data):
            for key in self.keys:
                if not np.all(self.data[key] == other.data[key]):
                    print('differing data for the samplet ids.')
                    return False
            return True
        else:
            return True


    def compatible(self, another):
        """
        Checks whether the input dataset is compatible with the current instance:
        i.e. with same set of subjects, each beloning to the same class.

        Parameters
        ----------
        dataset : MLdataset or similar

        Returns
        -------
        compatible : bool
            Boolean flag indicating whether two datasets are compatible or not
        """
        compatible, _ = check_compatibility([self, another])
        return compatible


def check_compatibility(datasets, reqd_num_features=None):
    """
    Checks whether the given MLdataset instances are compatible

    i.e. with same set of subjects, each beloning to the same class in all instances.

    Checks the first dataset in the list against the rest, and returns a boolean array.

    Parameters
    ----------
    datasets : Iterable
        A list of n datasets

    reqd_num_features : int
        The required number of features in each dataset.
        Helpful to ensure test sets are compatible with training set,
            as well as within themselves.

    Returns
    -------
    all_are_compatible : bool
        Boolean flag indicating whether all datasets are compatible or not

    compatibility : list
        List indicating whether first dataset is compatible with the rest individually.
        This could be useful to select a subset of mutually compatible datasets.
        Length : n-1

    dim_mismatch : bool
        Boolean flag indicating mismatch in dimensionality from that specified

    size_descriptor : tuple
        A tuple with values for (num_samples, reqd_num_features)
        - num_samples must be common for all datasets that are evaluated for compatibility
        - reqd_num_features is None (when no check on dimensionality is perfomed), or
            list of corresponding dimensionalities for each input dataset

    """

    from collections import Iterable
    if not isinstance(datasets, Iterable):
        raise TypeError('Input must be an iterable '
                        'i.e. (list/tuple) of MLdataset/similar instances')

    datasets = list(datasets)  # to make it indexable if coming from a set
    num_datasets = len(datasets)

    check_dimensionality = False
    dim_mismatch = False
    if reqd_num_features is not None:
        if isinstance(reqd_num_features, Iterable):
            if len(reqd_num_features) != num_datasets:
                raise ValueError('Specify dimensionality for exactly {} datasets.'
                                 ' Given for a different number {}'
                                 ''.format(num_datasets, len(reqd_num_features)))
            reqd_num_features = list(map(int, reqd_num_features))
        else:  # same dimensionality for all
            reqd_num_features = [int(reqd_num_features)] * num_datasets

        check_dimensionality = True
    else:
        # to enable iteration
        reqd_num_features = [None,] * num_datasets

    pivot = datasets[0]
    if not isinstance(pivot, MLDataset):
        pivot = MLDataset(pivot)

    if check_dimensionality and pivot.num_features != reqd_num_features[0]:
        warnings.warn('Dimensionality mismatch! Expected {} whereas current {}.'
                      ''.format(reqd_num_features[0], pivot.num_features))
        dim_mismatch = True

    compatible = list()
    for ds, reqd_dim in zip(datasets[1:], reqd_num_features[1:]):
        if not isinstance(ds, MLDataset):
            ds = MLDataset(ds)

        is_compatible = True
        # compound bool will short-circuit, not optim required
        if pivot.num_samples != ds.num_samples \
                or pivot.keys != ds.keys \
                or pivot.classes != ds.classes:
            is_compatible = False

        if check_dimensionality and reqd_dim != ds.num_features:
            warnings.warn('Dimensionality mismatch! Expected {} whereas current {}.'
                          ''.format(reqd_dim, ds.num_features))
            dim_mismatch = True

        compatible.append(is_compatible)

    return all(compatible), compatible, dim_mismatch, \
           (pivot.num_samples, reqd_num_features)