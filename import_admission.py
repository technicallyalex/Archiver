"""Bound import concurrency from observed fresh-probe throughput, not retries."""
class Admission:
    def __init__(self,maximum,now):
        self.maximum=maximum;self.limit=min(4,maximum);self.start=now;self.last=now
        self.count=0;self.previous=None;self.best=None;self.stable=maximum<=4

    def observe(self,now,fresh=False,failed=False):
        self.last=now
        if failed:
            self.limit=max(1,self.limit//2);self.stable=True;self.count=0;self.start=now
            return self.limit
        if not fresh or self.stable:return self.limit
        self.count+=1
        if self.count<self.limit*2 or now-self.start<1:return self.limit
        rate=self.count/(now-self.start)
        if self.previous:
            old_limit,old_rate=self.previous
            if rate<old_rate*1.1:
                self.limit=old_limit;self.stable=True
                return self.limit
        self.best=(self.limit,rate)
        if self.limit>=self.maximum:self.stable=True
        else:self.previous=self.best;self.limit=min(self.maximum,self.limit*2)
        self.start=now;self.count=0
        return self.limit

    def stalled(self,now):
        if now-self.last>=15:
            self.limit=max(1,self.limit//2);self.stable=True;self.last=now
        return self.limit
