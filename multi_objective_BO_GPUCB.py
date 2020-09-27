from single_objective_BO_GPUCB import *

def cmpToKey(mycmp):
    'Convert a cmp= function into a key= function'
    class K(object):
        def __init__(self,obj,*args):
            self.obj=obj
        def __lt__(self,other):
            return mycmp(self.obj,other.obj)<0
        def __gt__(self,other):
            return mycmp(self.obj,other.obj)>0
        def __eq__(self,other):
            return mycmp(self.obj,other.obj)==0
        def __le__(self,other):
            return mycmp(self.obj,other.obj)<=0  
        def __ge__(self,other):
            return mycmp(self.obj,other.obj)>=0
        def __ne__(self,other):
            return mycmp(self.obj,other.obj)!=0
    return K

class MultiObjectiveBOGPUCB(SingleObjectiveBOGPUCB):
    def __init__(self,problemBO,kappa=10.,nu=None,length_scale=1.):
        if nu is not None:
            kernel=Matern(nu=nu,length_scale=length_scale)
        else: kernel=RBF(length_scale=length_scale)
        self.gp=GaussianProcessScaled(kernel=kernel,n_restarts_optimizer=25,alpha=0.0001)
        self.problemBO=problemBO
        self.kappa=kappa
        if len(self.problemBO.metrics)==1:
            raise RuntimeError('MultiObjectiveBO passed with single metric!')
        
    def init(self,num_grid,log_path):
        coordinates=[np.linspace(vminVal,vmaxVal,num_grid) for vminVal,vmaxVal in zip(self.problemBO.vmin,self.problemBO.vmax)]
        if log_path is not None and os.path.exists(log_path+'/init.dat'):
            self.load(log_path+'/init.dat')
        else:
            self.points=np.array([dimi.flatten() for dimi in np.meshgrid(*coordinates)]).T.tolist()
            self.scores=self.problemBO.eval(self.points)
            if log_path is not None:
                self.save(log_path+'/init.dat')
        self.gp.fit(self.points,self.scores)
    
    def iterate(self):
        def obj(x,user_data):
            return -self.acquisition(x),0
        point,acquisition_val,ierror=DIRECT.solve(obj,self.problemBO.vmin,self.problemBO.vmax,logfilename='../direct.txt',algmethod=1)
        point=point.tolist()
        score=self.problemBO.eval([point])[0]
        self.points.append(point)
        self.scores.append(score)
        self.gp.fit(self.points,self.scores)
    
    def acquisition(self,x,user_data=None):
        #GP-UCB
        vol=1.
        sigmaSum=0.
        mu,sigma=self.gp.predict([x],return_std=True)
        vol*=np.product(mu[0])
        sigmaSum=np.sum(sigma[0])
        return vol+sigmaSum*self.kappa
    
    def run(self, num_grid=5, num_iter=100, log_path=None, log_interval=100, keep_latest=5):
        if log_path is not None and not os.path.exists(log_path):
            os.mkdir(log_path)
        if num_grid>0:
            self.init(num_grid,log_path)
        i=self.load_log(log_path,log_interval,keep_latest)
        while i<=num_iter:
            print("Multi-Objective BO Iter=%d!"%i)
            self.iterate()
            self.save_log(i,log_path,log_interval,keep_latest)
            i+=1
    
    def load(self,filename):
        self.points,self.scores=pickle.load(open(filename,'rb'))
        self.gp.fit(self.points,self.scores)
        
    def save(self,filename):
        pickle.dump((self.points,self.scores),open(filename,'wb'))
        
    def name(self):
        return 'MBO-GP-UCB('+self.problemBO.name()+')'
                 
    def get_best_on_metric(self,id):
        def obj(x,user_data):
            return -self.gp.predict([x])[0][id],0
        point,acquisition_val,ierror=DIRECT.solve(obj,self.problemBO.vmin,self.problemBO.vmax)
        return point

    def plot_iteration(self,plt,accumulate=False,eps=0.1):
        #plt
        yssAll=[]
        for i in range(len(self.problemBO.metrics)):
            scores=np.array([s[i] for s in self.scores])
            if accumulate:
                yss=np.maximum.accumulate(scores)
            else: yss=scores
            plt.plot(yss,'o-',label='Sampled points (%dth Metric)'%i)
            yssAll.append(yss)
        plt.title('Multi-Objective '+self.name()+('-accumulate' if accumulate else ''))
        plt.legend(loc='lower right')
        plt.xlabel('Iteration')
        plt.ylabel('Metric')
        
        #range rescaled
        vmin=None
        vmax=None
        for yss in yssAll:
            if vmin is None:
                vmin=yss.min()
                vmax=yss.max()
            else:
                vmin=min(vmin,yss.min())
                vmax=max(vmax,yss.max())
        vrng=vmax-vmin
        plt.ylim(vmin-vrng*eps,vmax+vrng*eps)
        return plt
    
    def plot_func_1D(self,plt,eps,res,repeat):
        assert len(self.problemBO.vmin)==1
        fig,ax=plt.subplots()
        ln_pt=[plt.plot([],[],'o',label='Sample (%dth Metric)'%m)[0] for m in range(len(self.problemBO.metrics))]
        ln_mean=[plt.plot([],[],'b-',label='Prediction (%dth Metric)'%m)[0] for m in range(len(self.problemBO.metrics))]
        ln_sigma=[plt.fill([],[],alpha=.5,fc='b',ec='None',label='.95 confidence interval (%dth Metric)'%m)[0] for m in range(len(self.problemBO.metrics))]
        ax.set_title('Multi-Objective '+self.name())
        
        gps=[]
        def init():
            #range
            ax.set_xlim(self.problemBO.vmin[0],self.problemBO.vmax[0])
            vmin=np.array(self.scores).min()
            vmax=np.array(self.scores).max()
            vrng=vmax-vmin
            ax.set_ylim(vmin-vrng*eps,vmax+vrng*eps)
            return ln_pt,ln_mean,ln_sigma
        
        def update(frame):
            if len(gps)==frame:
                gps.append(copy.deepcopy(self.gp))
                xdata=[self.points[i][0] for i in range(frame+1)]
                ydata=[self.scores[i] for i in range(frame+1)]
                gps[-1].fit([[i] for i in xdata],ydata)
            for m in range(len(self.problemBO.metrics)):
                #sampled points
                xdata=[self.points[i][0] for i in range(frame+1)]
                ydata=[self.scores[i][m] for i in range(frame+1)]
                ln_pt[m].set_data(xdata,ydata)
                
                #predicted mean of GP
                xdata=np.linspace(self.problemBO.vmin[0],self.problemBO.vmax[0],res).tolist()
                ydata,sdata=gps[frame].predict([[i] for i in xdata],return_std=True)
                ydata=ydata[:,m]
                sdata=sdata[:,m]
                ln_mean[m].set_data(xdata,ydata)
                
                #predicted variance of GP
                xdata=np.array(xdata)
                xdata=np.concatenate([xdata,xdata[::-1]])
                sdata=np.concatenate([ydata-1.9600*sdata,(ydata+1.9600*sdata)[::-1]])
                xsdata=np.stack([xdata,sdata],axis=1)
                ln_sigma[m].set_xy(xsdata)
            return ln_pt,ln_mean,ln_sigma
        
        from matplotlib.animation import FuncAnimation
        ani=FuncAnimation(fig,update,frames=[i for i in range(len(self.points))],init_func=init,blit=False,repeat=repeat)
        plt.legend(loc='lower right')
        return plt,ani

    def plot_func_2D(self,plt,eps,res,repeat):
        assert len(self.problemBO.vmin)==2
        coordinates=[np.linspace(vminVal,vmaxVal,res) for vminVal,vmaxVal in zip(self.problemBO.vmin,self.problemBO.vmax)]
        xsmesh,ysmesh=np.meshgrid(*coordinates)
        ptsmesh=np.array([dimi.flatten() for dimi in [xsmesh,ysmesh]]).T.tolist()
        zsmesh=self.gp.predict(ptsmesh).reshape((xsmesh.shape[0],xsmesh.shape[1],len(self.problemBO.metrics)))
        
        from mpl_toolkits import mplot3d
        from matplotlib import cm
        fig=plt.figure()
        ax=plt.axes(projection='3d')
        ln_pt=[ax.scatter(xs=[],ys=[],zs=[],label='Sample (%dth Metric)'%m) for m in range(len(self.problemBO.metrics))]
        ln_mean=[ax.plot_wireframe(X=xsmesh,Y=ysmesh,Z=zsmesh[:,:,m],label='Prediction (%dth Metric)'%m,color='red') for m in range(len(self.problemBO.metrics))]
        ax.set_title('Multi-Objective '+self.name())
        
        gps=[]
        def init():
            #range
            ax.set_xlim3d(self.problemBO.vmin[0],self.problemBO.vmax[0])
            ax.set_ylim3d(self.problemBO.vmin[1],self.problemBO.vmax[1])
            vmin=np.array(self.scores).min()
            vmax=np.array(self.scores).max()
            vrng=vmax-vmin
            ax.set_zlim3d(vmin-vrng*eps,vmax+vrng*eps)
            return ln_pt,ln_mean
        
        def update(frame):
            if len(gps)==frame:
                gps.append(copy.deepcopy(self.gp))
                xdata=[self.points[i][0] for i in range(frame+1)]
                ydata=[self.points[i][1] for i in range(frame+1)]
                zdata=[self.scores[i] for i in range(frame+1)]
                gps[-1].fit([[x,y] for x,y in zip(xdata,ydata)],zdata)
            for m in range(len(self.problemBO.metrics)):
                #sampled points
                xdata=[self.points[i][0] for i in range(frame+1)]
                ydata=[self.points[i][1] for i in range(frame+1)]
                zdata=[self.scores[i][m] for i in range(frame+1)]
                ln_pt[m]._offsets3d=(xdata,ydata,zdata)
                
                #predicted mean of GP
                xsmesh=ln_mean[m]._segments3d[:,:,0]
                ysmesh=ln_mean[m]._segments3d[:,:,1]
                ptsmesh=np.array([dimi.flatten() for dimi in [xsmesh,ysmesh]]).T.tolist()
                zsmesh=gps[frame].predict(ptsmesh)[:,m].reshape((xsmesh.shape[0],xsmesh.shape[1]))
                ln_mean[m]._segments3d=np.stack([xsmesh,ysmesh,zsmesh],axis=2)
            return ln_pt,ln_mean

        from matplotlib.animation import FuncAnimation
        ani=FuncAnimation(fig,update,frames=[i for i in range(len(self.points))],init_func=init,blit=False,repeat=repeat)
        plt.legend(loc='lower right')
        return plt,ani

    def build_pareto_front(self,num_grid):
        coordinates=[np.linspace(vminVal,vmaxVal,num_grid) for vminVal,vmaxVal in zip(self.problemBO.vmin,self.problemBO.vmax)]
        points=np.array([dimi.flatten() for dimi in np.meshgrid(*coordinates)]).T.tolist()
        on_front=[True for p in points]
        #compute score
        scores=self.gp.predict(points)
        #prune
        def govern(a,b):    #return if a govern b
            for m in range(len(self.problemBO.metrics)):
                if scores[a][m]<=scores[b][m]:
                    return False
            return True
        for i in range(len(on_front)):
            for j in range(i):
                if not on_front[i] or not on_front[j]:
                    continue
                elif govern(i,j):
                    on_front[j]=False
                elif govern(j,i):
                    on_front[i]=False
        #store
        front=[]
        for i in range(len(on_front)):
            if on_front[i]:
                front.append((points[i],[scores[i][m] for m in range(len(self.problemBO.metrics))]))
        return front
    
    def plot_front_2D(self,front):
        #sort by polar angle
        min0=min([f[1][0] for f in front])
        min1=min([f[1][1] for f in front])
        def get_polar(A):
            x,y=A[1][0]-min0,A[1][1]-min1
            return math.atan2(y,x)
        def cmp(A,B):
            return get_polar(A)-get_polar(B)
        front=sorted(front,key=cmpToKey(cmp))
        
        #plot
        import matplotlib.pyplot as plt   
        xss=[s[0] for p,s in front]
        yss=[s[1] for p,s in front]
        plt.plot(xss,yss,'o-',label='Sampled points')
        plt.title('Pareto-Front 2D')
        plt.legend(loc='lower right')
        plt.xlabel(type(self.problemBO.metrics[0]).__name__)
        plt.ylabel(type(self.problemBO.metrics[1]).__name__)
        plt.show()
    
    def plot_front_3D(self,front):
        #plot
        import matplotlib.pyplot as plt   
        xss=[s[0] for p,s in front]
        yss=[s[1] for p,s in front]
        zss=[s[2] for p,s in front]
        ax=plt.axes(projection='3d')
        ax.scatter(xss,yss,zss,'o',label='Sampled points')
        ax.set_title('Pareto-Front 3D')
        ax.legend(loc='lower right')
        ax.set_xlabel(type(self.problemBO.metrics[0]).__name__)
        ax.set_ylabel(type(self.problemBO.metrics[1]).__name__)
        ax.set_zlabel(type(self.problemBO.metrics[2]).__name__)
        plt.show()
    
    def plot_pareto_front(self,num_grid):
        front=self.build_pareto_front(num_grid)
        if len(self.problemBO.metrics)==2:
            self.plot_front_2D(front)
        elif len(self.problemBO.metrics)==3:
            self.plot_front_3D(front)
        else: raise RuntimeError('Plotting domain dimension > 2 is not supported!')

if __name__=='__main__':
    problem=Test1D2MProblemBO()
    BO=MultiObjectiveBOGPUCB(problem)
    debug_toy_problem(BO)
    BO.plot_pareto_front(128)
    
    problem=Test2D3MProblemBO()
    BO=MultiObjectiveBOGPUCB(problem)
    debug_toy_problem(BO)
    BO.plot_pareto_front(128)
    
    from reach_problem_BO import *
    objects=[(-0.5,1.0),(0.0,1.0),(0.5,1.0)]
    obstacles=[Circle((-0.35,0.5),0.2),Circle((0.35,0.5),0.2)]
    reach=ReachProblemBO(objects=objects,obstacles=obstacles,policy_space=[('angle0',5),('angle1',5)])
    
    num_grid=2
    num_iter=100
    BO=MultiObjectiveBOGPUCB(reach)
    path='../'+BO.name()+'.dat'
    if not os.path.exists(path):
        BO.run(num_grid=num_grid,num_iter=num_iter)
        BO.save(path)
    else:
        BO.load(path)
    reach.visualize(BO.get_best_on_metric(1))