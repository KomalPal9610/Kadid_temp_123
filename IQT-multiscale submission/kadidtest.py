import os
import torch
import torchvision

from model.model_main import IQARegression
from model.backbone import inceptionresnetv2, Mixed_5b, Block35, SaveOutput
from option.config import Config

import cv2
import numpy as np

from tqdm import tqdm

# config file
config = Config({
    # device
    "GPU_ID": "0",
    "scale": 1,

    # model for PIPAL (NTIRE2022 Challenge)
    # "n_enc_seq": 21*21,                 # feature map dimension (H x W) from backbone, this size is related to crop_size
    # "n_dec_seq": 21*21,                 # feature map dimension (H x W) from backbone
    # "n_layer": 1,                       # number of encoder/decoder layers
    # "d_hidn": 128,                      # input channel (C) of encoder / decoder (input: C x N)
    # "i_pad": 0,
    # "d_ff": 1024,                       # feed forward hidden layer dimension
    # "d_MLP_head": 128,                  # hidden layer of final MLP
    # "n_head": 4,                        # number of head (in multi-head attention)
    # "d_head": 128,                      # input channel (C) of each head (input: C x N) -> same as d_hidn
    # "dropout": 0.1,                     # dropout ratio of transformer
    # "emb_dropout": 0.1,                 # dropout ratio of input embedding
    # "layer_norm_epsilon": 1e-12,
    # "n_output": 1,                      # dimension of final prediction
    # "crop_size": 192,                   # input image crop size
    "n_enc_seq": 29 * 29,  # feature map dimension (H x W) from backbone, this size is related to crop_size
    "n_dec_seq": 29 * 29,  # feature map dimension (H x W) from backbone
    "n_layer": 2,  # number of encoder/decoder layers
    "d_hidn": 256,  # input channel (C) of encoder / decoder (input: C x N)
    "i_pad": 0,
    "d_ff": 1024,  # feed forward hidden layer dimension
    "d_MLP_head": 512,  # hidden layer of final MLP
    "n_head": 4,  # number of head (in multi-head attention)
    "d_head": 256,  # input channel (C) of each head (input: C x N) -> same as d_hidn
    "dropout": 0.1,  # dropout ratio of transformer
    "emb_dropout": 0.1,  # dropout ratio of input embedding
    "layer_norm_epsilon": 1e-12,
    "n_output": 1,  # dimension of final prediction
    "crop_size": 256,

    # data
    "db_path": "/home/vj/Documents/kadid10k/images",
    "weight_file": "/home/vj/PycharmProjects/IQA_final/IQA-multiscaling-main/IQT-multiscale submission/weights/scale1_epoch128.pth",
    # "./weights/Scale1.pth", "./weights/Scale2.pth", "./weights/Scale3.pth"
    "result_file": "kadidscale1.txt",  # "outputScale1.txt","outputScale2.txt","outputScale3.txt"

    # ensemble in test
    "test_ensemble": True,
    "n_ensemble": 20
})
config.device = torch.device("cuda:%s" % config.GPU_ID if torch.cuda.is_available() else "cpu")
if torch.cuda.is_available():
    print('Using GPU %s' % config.GPU_ID)
else:
    print('Using CPU')


def scaling(img, size):
    S = int(img.shape[1] // size)
    output = cv2.resize(img, (S, S), interpolation=cv2.INTER_AREA)
    return output


# create_model
model_transformer = IQARegression(config).to(config.device)
model_backbone = inceptionresnetv2(num_classes=1001, pretrained='imagenet+background').to(config.device)

# save intermediate layers
save_output = SaveOutput()
hook_handles = []
for layer in model_backbone.modules():
    if isinstance(layer, Mixed_5b):
        handle = layer.register_forward_hook(save_output)
        hook_handles.append(handle)
    elif isinstance(layer, Block35):
        handle = layer.register_forward_hook(save_output)
        hook_handles.append(handle)

# load weights
if config.weight_file is not None:
    checkpoint = torch.load(config.weight_file)
    model_transformer.load_state_dict(checkpoint['model_state_dict'])

    model_transformer.eval()
    model_backbone.eval()
else:
    raise ValueError('You need to specify a weight file.')

import pandas as pd


def Random_crop( img):
    h, w, c = img.shape
    new_h, new_w = 256, 256
    top = np.random.randint(0, h - new_h)
    left = np.random.randint(0, w - new_w)

    img = img[top: top + new_h, left: left + new_w, :]
    return img
df = pd.read_csv("/home/vj/PycharmProjects/IQA_final/IQA-multiscaling-main/IQT-multiscale submission/kadid_test_file.txt", sep='\t',usecols=[0,1,2], names=['A', 'B','C'])
# test images
df = df.reset_index()

f = open(config.result_file, 'w')
for index, row in tqdm(df.iterrows()):
    d_img_name = os.path.join(config.db_path, row['B'])
    ext = os.path.splitext(d_img_name)[-1]

    enc_inputs = torch.ones(1, config.n_enc_seq + 1).to(config.device)
    dec_inputs = torch.ones(1, config.n_dec_seq + 1).to(config.device)
    if ext == '.bmp'or '.BMP':
        # reference image
        r_img_name = row['A']
        r_img = cv2.imread(os.path.join(config.db_path, row['A']), cv2.IMREAD_COLOR)
        r_img = Random_crop(r_img)
        if config.scale != 1:
            r_img = scaling(r_img, config.scale)
        r_img = cv2.cvtColor(r_img, cv2.COLOR_BGR2RGB)
        r_img = np.array(r_img).astype('float32') / 255
        r_img = (r_img - 0.5) / 0.5
        r_img = np.transpose(r_img, (2, 0, 1))
        r_img = torch.from_numpy(r_img)

        # distoted image
        d_img = cv2.imread(os.path.join(config.db_path, d_img_name), cv2.IMREAD_COLOR)
        d_img = Random_crop(d_img)
        if config.scale != 1:
            d_img = scaling(d_img, config.scale)
        d_img = cv2.cvtColor(d_img, cv2.COLOR_BGR2RGB)
        d_img = np.array(d_img).astype('float32') / 255
        d_img = (d_img - 0.5) / 0.5
        d_img = np.transpose(d_img, (2, 0, 1))
        d_img = torch.from_numpy(d_img)

        pred = 0
        # inference (use ensemble or not)
        if config.test_ensemble:
            for i in range(config.n_ensemble):
                c, h, w = r_img.size()
                if config.scale == 1:
                    new_h = config.crop_size
                    new_w = config.crop_size
                    top = np.random.randint(0, h - new_h+1)
                    left = np.random.randint(0, w - new_w+1)
                else:
                    new_h = h
                    new_w = w
                    top = np.random.randint(0, h - new_h + 1)
                    left = np.random.randint(0, w - new_w + 1)

                r_img_crop = r_img[:, top: top + new_h, left: left + new_w].unsqueeze(0)
                d_img_crop = d_img[:, top: top + new_h, left: left + new_w].unsqueeze(0)

                r_img_crop = r_img_crop.to(config.device)
                d_img_crop = d_img_crop.to(config.device)
                feat_ref, feat_diff = model_backbone(r_img_crop, d_img_crop, save_output)
                if config.scale != 1:
                    feat_ref = torch.nn.functional.interpolate(feat_ref, size=(29, 29), mode='bilinear',
                                                               align_corners=True)
                    feat_diff = torch.nn.functional.interpolate(feat_diff, size=(29, 29), mode='bilinear',
                                                                align_corners=True)

                enc_inputs_embed = feat_diff
                dec_inputs_embed = feat_ref
                pred += model_transformer(enc_inputs, enc_inputs_embed, dec_inputs, dec_inputs_embed)

            pred /= config.n_ensemble

        else:
            c, h, w = r_img.size()
            if config.scale == 1:
                new_h = config.crop_size
                new_w = config.crop_size
                top = np.random.randint(0, h - new_h+1)
                left = np.random.randint(0, w - new_w+1)
            else:
                new_h = h
                new_w = w
                top = np.random.randint(0, h - new_h + 1)
                left = np.random.randint(0, w - new_w + 1)

            r_img_crop = r_img[:, top: top + new_h, left: left + new_w].unsqueeze(0)
            d_img_crop = d_img[:, top: top + new_h, left: left + new_w].unsqueeze(0)

            r_img_crop = r_img_crop.to(config.device)
            d_img_crop = d_img_crop.to(config.device)
            feat_ref, feat_diff = model_backbone(r_img_crop, d_img_crop, save_output)
            if config.scale != 1:
                feat_ref = torch.nn.functional.interpolate(feat_ref, size=(29, 29), mode='bilinear', align_corners=True)
                feat_diff = torch.nn.functional.interpolate(feat_diff, size=(29, 29), mode='bilinear',
                                                            align_corners=True)
            enc_inputs_embed = feat_diff
            dec_inputs_embed = feat_ref

            pred = model_transformer(enc_inputs, enc_inputs_embed, dec_inputs, dec_inputs_embed)

        line = "%s,%f\n" % (row['B'], float(pred.item()))
        f.write(line)
f.close()

