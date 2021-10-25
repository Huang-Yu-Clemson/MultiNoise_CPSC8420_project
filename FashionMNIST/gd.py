import os
import argparse
import numpy as np
import torch
from tensorboardX import SummaryWriter

from mnist import FashionMNIST
from net import ConvSmall
from utils import *

parser = argparse.ArgumentParser()
parser.add_argument('--seed', type=int, default=1234)
parser.add_argument('--iters', type=int, default=int(1e4+1))
parser.add_argument('--batchsize', type=int, default=1000)
parser.add_argument('--lr', type=float, default=0.01)
parser.add_argument('--resume', type=str, default=None)
parser.add_argument('--datadir', type=str, default='MultiNoise-master/FashionMNIST/cl1000/')
parser.add_argument('--logdir', type=str, default='MultiNoise-master/FashionMNIST/logs/GD')

args = parser.parse_args()
logger = LogSaver(args.logdir)
logger.save(str(args), 'args')

# seed
np.random.seed(args.seed)
torch.manual_seed(args.seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

# data
dataset = FashionMNIST(args.datadir)
logger.save(str(dataset), 'dataset')
train_list = dataset.getTrainList(args.batchsize, True)
test_list = dataset.getTestList(10000, True)

# model
model = ConvSmall().cuda()
start_iter = 0
lr = args.lr
criterion = torch.nn.CrossEntropyLoss().cuda()
optimizer = torch.optim.SGD(model.parameters(), lr=lr)
if args.resume:
    checkpoint = torch.load(args.resume)
    start_iter = checkpoint['iter'] + 1
    lr = checkpoint['lr']
    model.load_state_dict(checkpoint['model'])
    optimizer.load_state_dict(checkpoint['optimizer'])
    logger.save("=> loaded checkpoint '{}'".format(args.resume))
logger.save(str(model), 'classifier')
logger.save(str(optimizer), 'optimizer')

# writer
writer = SummaryWriter(args.logdir)

# optimization
for i in range(start_iter, args.iters):
    # train
    model.train()
    optimizer.zero_grad()
    train_loss, train_acc = 0, 0
    for x,y in train_list:
        out = model(x)
        loss = criterion(out, y)
        loss.backward()
        train_acc += accuracy(out, y).item()
        train_loss += loss.item()
    for param in model.parameters():
        param.grad.data /= len(train_list)
    optimizer.step()
    train_acc /= len(train_list)
    train_loss /= len(train_list)

    # evaluate
    if i % 100 == 0 or i <= 100:
        model.eval()
        writer.add_scalar('lr', lr, i)
        writer.add_scalar('acc/train', train_acc, i)
        writer.add_scalar('loss/train', train_loss, i)

        test_loss, test_acc = 0, 0
        for x,y in test_list:
            out = model(x)
            test_loss += criterion(out, y).item()
            test_acc += accuracy(out, y).item()
        test_loss /= len(test_list)
        test_acc /= len(test_list)
        writer.add_scalar('loss/test', test_loss, i)
        writer.add_scalar('acc/test', test_acc, i)
        writer.add_scalar('acc/diff', train_acc - test_acc, i)

        logger.save('Iter:%d, Test [acc: %.2f, loss: %.4f], Train [acc: %.2f, loss: %.4f]' \
                % (i, test_acc, test_loss, train_acc, train_loss))

    if i % 1000 == 0:
        state = {'iter':i, 'lr':lr, 'model':model.state_dict(), 'optimizer':optimizer.state_dict()}
        torch.save(state, args.logdir+'/iter-'+str(i)+'.pth.tar')

writer.close()
