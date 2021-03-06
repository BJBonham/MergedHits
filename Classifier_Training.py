import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve, auc
from IPython.display import FileLink, FileLinks
from sklearn.model_selection import train_test_split
import matplotlib
matplotlib.use('Agg') # for use without ssh -Y
import matplotlib.pyplot as plt


# The main inputs you may want to vary
fileNumber = 1
entriesStop = 500 # "entries_stop=None" to use all entries
maxEpochs=100
earlyStoppingPatience = 5
otherVariables = ["totalADCcount"]


def GetData(testTrainFrac=.5):
    from keras.utils import to_categorical
    global filename, signalstring
    
    filenames=["/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/SharedHits/NormalizedCharge/output_final.h5",
               "/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/SharedHits/AbsoluteCharge/output_final.h5",
               "/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/Shared100NonShared/NormalizedCharge/output_final.h5",
               "/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/Shared100NonShared/AbsoluteCharge/output_final.h5",
               "/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/AllHits/NormalizedCharge/output_final.h5",
               "/uscms_data/d3/bbonham/TrackerProject/Output_of_Postprocess/AllHits/AbsoluteCharge/output_final.h5"]
    filename = filenames[fileNumber]
    
    # Signal Region for files with only shared hits
    if fileNumber in [0,1]:
        signalstring = "['nUniqueSimTracksInSharedHit']>1"
    # Signal Region for files with shared and nonshared hits
    if fileNumber in [2,3,4,5]:
        signalstring = "['isSharedHit']==1"
        #signalstring = "['nUniqueSimTracksInSharedHit']>1"
    
    df = pd.read_hdf(filename, key='df', mode='r', start=0, stop=entriesStop)
    print '\nFile: '+filename
    print 'df size:',round(df.memory_usage().sum()/(1024.**2),1),"MB"
    
    # Scale down the totalADCcount
    df[['totalADCcount']] = df[['totalADCcount']]/10000
   
    # Reset the indices in case rows have the same index (maybe caused by two-lambda events/vertices?)
    df = df.set_index(np.arange(df.shape[0]))

    df_train,df_test = train_test_split(df, test_size=testTrainFrac, random_state=10)

    images_train = to_image(df_train)
    images_test = to_image(df_test)

    num_otherVariables = len(otherVariables)
    otherVariables_train = df_train[otherVariables]
    otherVariables_test = df_test[otherVariables]
    
    train_data = [images_train, otherVariables_train]
    test_data = [images_test, otherVariables_test]
    
    train_labels = to_categorical(eval("df_train"+signalstring))
    test_labels = to_categorical(eval("df_test"+signalstring))

    print("training data: s={}, b={}".format(int(sum(train_labels[:,1])),int(sum(train_labels[:,0]))))
    print("testing data: s={}, b={}\n".format(int(sum(test_labels[:,1])),int(sum(test_labels[:,0]))))

    return train_data, test_data, train_labels, test_labels


def DefineModel(size=20):
    #Define model with Keras's functional API, not sequential, to combine network types
    from keras.layers import Input,Conv2D,Dense,concatenate,Flatten
    from keras.models import Model
    inputClusterImages = Input(shape=(size,size,1))
    inputHitVariables = Input(shape=(len(otherVariables),))

    #CNN on cluster images
    CNN = Conv2D(32, kernel_size=(8,8),padding='same',activation='relu')(inputClusterImages)
    CNN = Conv2D(32, kernel_size=(4,4),padding='same',activation='relu')(CNN)
    CNN = Flatten()(CNN)

    CNN = Model(inputs=inputClusterImages,outputs=CNN)
    
    #NN on the Hit variables
    NN = Dense(5,activation='relu')(inputHitVariables)
    NN = Model(inputs=inputHitVariables,outputs=NN)

    combined_outputs = concatenate([CNN.output,NN.output])
    combination_NN = Dense(50, activation='relu')(combined_outputs)
    combination_NN = Dense(2,activation='softmax')(combination_NN)

    full_classifier = Model(inputs=[CNN.input,NN.input],outputs=combination_NN)
    full_classifier.compile(loss='categorical_crossentropy', optimizer="adam", metrics = ["accuracy"])
    full_classifier.summary()

    return full_classifier


def to_image(df,size=20):
    pixels = ["pixel_{0}".format(i) for i in range(size**2)]
    return  np.expand_dims(np.expand_dims(df[pixels], axis=-1).reshape(-1,size,size), axis=-1)
    

def TrainModel(classifier,data,labels,validation_split=0.1):
    from keras.callbacks import EarlyStopping, ModelCheckpoint
    early_stopping = EarlyStopping(monitor='val_loss', patience=earlyStoppingPatience) # early epoch stopping
    
    classifier.fit(data, labels, epochs=maxEpochs, validation_split=validation_split, callbacks=[early_stopping])
    classifier.save('TrainedClassifier_'+filename[60:-16].replace('/','_')+'.h5')
    
    
def EvaluateModel(classifier,data,labels):
    discriminants = classifier.predict(data)
    return discriminants[:,1]


def PlotROC(classifier,discriminants,labels):
    fpr_keras, tpr_keras, thresholds_keras = roc_curve(labels[:,1], discriminants)
    auc = np.trapz(tpr_keras,fpr_keras) 
    print("ROC curve area: {:.3f}".format(auc))
    
    plt.plot(fpr_keras, tpr_keras, label='Keras (area = {:.3f})'.format(auc))
    plt.xlabel('False positive rate')
    plt.ylabel('True positive rate')
    plt.title('ROC Curve (Area = {:.3f})'.format(auc)+'\n'+filename[60:-16]+'\n'+str(otherVariables)+'\nSignal: '+signalstring)
    plt.tight_layout()
    plt.savefig('ROC_'+filename[60:-16].replace('/','_')+'.png')
    plt.close()
    

def PlotDiscriminants(train_probs,train_Y,test_probs,test_Y):
    train_signal_probs = train_probs[train_Y[:,0]==1]
    train_bkg_probs = train_probs[train_Y[:,0]!=1]

    test_signal_probs = test_probs[test_Y[:,0]==1]
    test_bkg_probs = test_probs[test_Y[:,0]!=1]

    plt.hist(test_signal_probs, color = 'b', label = 'Signal (test)', range = (0,1), bins = 30,histtype='step', log=True)
    plt.hist(test_bkg_probs, color = 'r', label = 'Background (test)', range = (0,1), bins = 30,histtype='step', log=True)
    plt.hist(train_signal_probs,linestyle='--', alpha = 0.5, color = 'b', label = 'Signal (train)', range = (0,1), bins = 30,histtype='step',log=True)
    plt.hist(train_bkg_probs,linestyle='--', color = 'r', alpha = 0.5, label = 'Background (train)', range = (0,1), bins = 30,histtype='step',log=True)
    plt.legend(loc='best')
    plt.xlabel('Discriminant')
    plt.title('CNN Signal and Background Discriminants')
    plt.savefig('disc_'+filename[60:-16].replace('/','_')+'.png')
    plt.close()


def Run():
    train_X, test_X, train_Y, test_Y = GetData()
    model = DefineModel()
    TrainModel(model,train_X,train_Y)
    train_probs = EvaluateModel(model,train_X,train_Y)
    test_probs = EvaluateModel(model,test_X,test_Y)
    PlotROC(model,test_probs,test_Y)
    PlotDiscriminants(train_probs,train_Y,test_probs,test_Y)

Run()