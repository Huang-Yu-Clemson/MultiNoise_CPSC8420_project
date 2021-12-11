## SVHN experiments

The code generates Figure 3

### Requirement
1. Python 3.6
2. PyTorch 1.0.0 with GPU support
3. TensorboardX


#### Generate data
`python svhn2np.py`

#### Test the performance of the compared methods

- MSGD-Fisher: `python ggd.py`
- MSGD-Cov: `python ggdCov.py`
- MSGD-[Fisher-B]: `python gdStoF.py`
- MSGD-[Cov-B]: `python gdStoCov.py`

