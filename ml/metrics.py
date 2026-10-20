import numpy as np

NAMES=('cutoff','attack','release')


def to_physical(normalized,spec):
    result=np.empty_like(np.asarray(normalized),dtype=np.float64)
    for i,name in enumerate(NAMES):
        p=spec['parameters'][name]
        result[:,i]=p['minimum']+(p['maximum']-p['minimum'])*np.clip(normalized[:,i],0,1)**(1/p['skew'])
    return result


def to_normalized(physical,spec):
    result=np.empty_like(np.asarray(physical),dtype=np.float64)
    for i,name in enumerate(NAMES):
        p=spec['parameters'][name]
        result[:,i]=np.clip((physical[:,i]-p['minimum'])/(p['maximum']-p['minimum']),0,1)**p['skew']
    return result


def score(predicted,normalized_truth,physical_truth,spec):
    physical=to_physical(predicted,spec)
    result={'normalized_mse':float(np.mean((np.asarray(predicted,dtype=np.float64)-normalized_truth)**2)), 'parameters':{}}
    for i,name in enumerate(NAMES):
        scale=1 if name=='cutoff' else 1000
        error=(physical[:,i]-physical_truth[:,i])*scale
        result['parameters'][name]={'unit':'Hz' if i==0 else 'ms','mae':float(np.mean(np.abs(error))),
                                   'rmse':float(np.sqrt(np.mean(error**2))),
                                   'normalized_mse':float(np.mean((predicted[:,i]-normalized_truth[:,i])**2))}
    return result
