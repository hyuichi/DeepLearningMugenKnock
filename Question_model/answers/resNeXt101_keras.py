import keras
import cv2
import numpy as np
import argparse
from glob import glob
import copy

# GPU config
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import tensorflow as tf
from keras import backend as K
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
config.gpu_options.visible_device_list="0"
sess = tf.Session(config=config)
K.set_session(sess)

# network
from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, Activation, Flatten, Conv2D, MaxPooling2D, Input, BatchNormalization, concatenate, AveragePooling2D, Add, SeparableConv2D

num_classes = 2
img_height, img_width = 128, 128
channel = 3

def ResNeXt101():

    def Block(x, in_f, f_1, out_f, stride=1, cardinality):
        res_x = Conv2D(f_1, [1, 1], strides=stride, padding='same', activation=None)(x)
        res_x = BatchNormalization()(res_x)
        res_x = Activation("relu")(res_x)

        multiplier = f_1 // cardinality
        res_x = SeparableConv2D(f_1, [3, 3], strides=1, padding='same', depth_multiplier=multiplier, activation=None)(res_x)
        res_x = BatchNormalization()(res_x)
        res_x = Activation("relu")(res_x)

        res_x = Conv2D(out_f, [1, 1], strides=1, padding='same', activation=None)(res_x)
        res_x = BatchNormalization()(res_x)
        res_x = Activation("relu")(res_x)

        if in_f != out_f:
            x = Conv2D(out_f, [1, 1], strides=1, padding="same", activation=None)(x)
            x = BatchNormalization()(x)
            x = Activation("relu")(x)

        if stride == 2:
            x = MaxPooling2D([2, 2], strides=2, padding="same")(x)
        
        x = Add()([res_x, x])

        return x
        
    
    inputs = Input((img_height, img_width, channel))
    x = inputs
    
    x = Conv2D(64, [7, 7], strides=2, padding='same', activation=None)(x)
    x = BatchNormalization()(x)
    x = Activation("relu")(x)
    x = MaxPooling2D([3, 3], strides=2, padding='same')(x)

    x = Block(x, 64, 64, 256)
    x = Block(x, 256, 64, 256)
    x = Block(x, 256, 64, 256)

    x = Block(x, 256, 128, 512, stride=2)
    x = Block(x, 512, 128, 512)
    x = Block(x, 512, 128, 512)
    x = Block(x, 512, 128, 512)

    x = Block(x, 512, 256, 1024, stride=2)
    for i in range(22):
        x = Block(x, 1024, 256, 1024)

    x = Block(x, 1024, 512, 2048, stride=2)
    x = Block(x, 2048, 256, 2048)
    x = Block(x, 2048, 256, 2048)

    x = AveragePooling2D([img_height // 32, img_width // 32], strides=1, padding='valid')(x)
    x = Flatten()(x)
    x = Dense(num_classes, activation='softmax', name='out')(x)

    model = Model(inputs=inputs, outputs=[x])

    return model
    


CLS = ['akahara', 'madara']


# get train data
def data_load(path, hf=False, vf=False, rot=False):
    xs = []
    ts = []
    paths = []
    
    for dir_path in glob(path + '/*'):
        for path in glob(dir_path + '/*'):
            x = cv2.imread(path)
            x = cv2.resize(x, (img_width, img_height)).astype(np.float32)
            x /= 255.
            x = x[..., ::-1]
            xs.append(x)

            t = [0 for _ in range(num_classes)]
            for i, cls in enumerate(CLS):
                if cls in path:
                    t[i] = 1
            
            ts.append(t)

            paths.append(path)

            if hf:
                xs.append(x[:, ::-1])
                ts.append(t)
                paths.append(path)

            if vf:
                xs.append(x[::-1])
                ts.append(t)
                paths.append(path)

            if hf and vf:
                xs.append(x[::-1, ::-1])
                ts.append(t)
                paths.append(path)

            if rot != False:
                angle = rot
                scale = 1

                # show
                a_num = 360 // rot
                w_num = np.ceil(np.sqrt(a_num))
                h_num = np.ceil(a_num / w_num)
                count = 1
                #plt.subplot(h_num, w_num, count)
                #plt.axis('off')
                #plt.imshow(x)
                #plt.title("angle=0")
                
                while angle < 360:
                    _h, _w, _c = x.shape
                    max_side = max(_h, _w)
                    tmp = np.zeros((max_side, max_side, _c))
                    tx = int((max_side - _w) / 2)
                    ty = int((max_side - _h) / 2)
                    tmp[ty: ty+_h, tx: tx+_w] = x.copy()
                    M = cv2.getRotationMatrix2D((max_side/2, max_side/2), angle, scale)
                    _x = cv2.warpAffine(tmp, M, (max_side, max_side))
                    _x = _x[tx:tx+_w, ty:ty+_h]
                    xs.append(_x)
                    ts.append(t)
                    paths.append(path)

                    # show
                    #count += 1
                    #plt.subplot(h_num, w_num, count)
                    #plt.imshow(_x)
                    #plt.axis('off')
                    #plt.title("angle={}".format(angle))

                    angle += rot
                #plt.show()


    xs = np.array(xs, dtype=np.float32)
    ts = np.array(ts, dtype=np.int)

    return xs, ts, paths


# train
def train():
    model = ResNeXt101()

    for layer in model.layers:
        layer.trainable = True

    model.compile(
        loss='categorical_crossentropy',
        optimizer=keras.optimizers.SGD(lr=0.001, decay=1e-6, momentum=0.9, nesterov=True),
        metrics=['accuracy'])

    xs, ts, paths = data_load('../Dataset/train/images', hf=True, vf=True, rot=1)

    # training
    mb = 16
    mbi = 0
    train_ind = np.arange(len(xs))
    np.random.seed(0)
    np.random.shuffle(train_ind)
    for i in range(500):
        if mbi + mb > len(xs):
            mb_ind = copy.copy(train_ind)[mbi:]
            np.random.shuffle(train_ind)
            mb_ind = np.hstack((mb_ind, train_ind[:(mb-(len(xs)-mbi))]))
            mbi = mb - (len(xs) - mbi)
        else:
            mb_ind = train_ind[mbi: mbi+mb]
            mbi += mb

        x = xs[mb_ind]
        t = ts[mb_ind]

        loss, acc = model.train_on_batch(x=x, y={'out':t})

        if (i+1) % 10 == 0:
            print("iter >>", i+1, ", loss >>", loss_total, ', accuracy >>', acc)

    model.save('model.h5')

# test
def test():
    # load trained model
    model = ResNeXt101()
    model.load_weights('model.h5')

    xs, ts, paths = data_load("../Dataset/test/images/")

    for i in range(len(paths)):
        x = xs[i]
        t = ts[i]
        path = paths[i]
        
        x = np.expand_dims(x, axis=0)
        
        pred = model.predict_on_batch(x)[0]
        print("in {}, predicted probabilities >> {}".format(path, pred))
    

def arg_parse():
    parser = argparse.ArgumentParser(description='CNN implemented with Keras')
    parser.add_argument('--train', dest='train', action='store_true')
    parser.add_argument('--test', dest='test', action='store_true')
    args = parser.parse_args()
    return args

# main
if __name__ == '__main__':
    args = arg_parse()

    if args.train:
        train()
    if args.test:
        test()

    if not (args.train or args.test):
        print("please select train or test flag")
        print("train: python main.py --train")
        print("test:  python main.py --test")
        print("both:  python main.py --train --test")
