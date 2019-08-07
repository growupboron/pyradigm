import numpy as np

from pyradigm import ClassificationDataset as ClfDataset, MultiDataset
from pyradigm.utils import make_random_ClfDataset

min_num_modalities = 3
max_num_modalities = 10
max_feat_dim = 10


def make_fully_separable_classes(max_class_size=10, max_dim=22):
    from sklearn.datasets import make_blobs

    random_center = np.random.rand(max_dim)
    cluster_std = 1.5
    centers = [random_center, random_center + cluster_std * 6]
    blobs_X, blobs_y = make_blobs(n_samples=max_class_size, n_features=max_dim,
                                  centers=centers, cluster_std=cluster_std)

    unique_labels = np.unique(blobs_y)
    class_ids = {lbl: str(lbl) for lbl in unique_labels}

    new_ds = ClfDataset()
    for index, row in enumerate(blobs_X):
        new_ds.add_samplet('sub{}'.format(index),
                           row, class_ids[blobs_y[index]])

    return new_ds


def new_dataset_with_same_ids_classes(in_ds):
    feat_dim = np.random.randint(1, max_feat_dim)
    out_ds = ClfDataset()
    for id_ in in_ds.samplet_ids:
        out_ds.add_samplet(id_,
                           np.random.rand(feat_dim),
                           target=in_ds.targets[id_])
    return out_ds


# ds = make_fully_separable_classes()
ds = make_random_ClfDataset(5, 20, 50, 10, stratified=False)

num_modalities = np.random.randint(min_num_modalities, max_num_modalities)

multi = MultiDataset()
for ii in range(num_modalities):
    multi.append(new_dataset_with_same_ids_classes(ds), identifier=ii)

# for trn, tst in multi.holdout(num_rep=5, return_ids_only=True):
#     print('train: {}\ntest: {}\n'.format(trn, tst))

print(multi)

return_ids_only = False
for trn, tst in multi.holdout(num_rep=5, train_perc=0.51, stratified=True,
                              return_ids_only=return_ids_only):
    if return_ids_only:
        print('train: {}\ttest: {}\n'.format(len(trn), len(tst)))
    else:
        for aa, bb in zip(trn, tst):
            if aa.num_features != bb.num_features:
                raise ValueError('train and test dimensionality do not match!')

            print('train: {}\ntest : {}\n'.format(aa.shape, bb.shape))

print()
