"""Coverage budgets: test depth changes evidence, never the quality target."""
LEVELS = {
    'fast': {'label':'Fast','probeScale':.5,'probeMin':8,'probeMax':24,'samples':3,'longSamples':3,'holdouts':1,'rounds':3,'expansions':0},
    'balanced': {'label':'Balanced','probeScale':1.,'probeMin':12,'probeMax':48,'samples':6,'longSamples':8,'holdouts':None,'rounds':4,'expansions':1},
    'extensive': {'label':'Extensive','probeScale':1.5,'probeMin':18,'probeMax':72,'samples':10,'longSamples':12,'holdouts':4,'rounds':5,'expansions':2},
}
def policy(value='balanced'):
    if not isinstance(value,str) or value not in LEVELS:
        raise ValueError('Choose Fast, Balanced or Extensive testing')
    return LEVELS[value]

def holdout_count(level, samples):
    return policy(level)['holdouts'] or max(2,min(4,samples//2))
