部署的时候需要注意如下几点：（以在虚拟机Ubuntu中部署为例）

1. 使用的虚拟机是Ubuntu 18.04, 默认安装了Python3，需要安装Python2，也可以不安装Python2
    其中Python3需要是3.6以上
        Python2需要是2.7以上

2. 安装ssh server，并配置通过key访问；
    （1）安装ssh server：sudo apt-get install openssh-server
    （2）重启ssh server：sudo /etc/init.d/ssh restart
    （3）为 SSH 用户建立私钥和公钥：ssh-keygen
    （4）修改公钥名称：cd ~/.ssh     mv id_rsa.pub authorized_keys
    （5）将私钥id_rsa拷走到即将进行登录操作的机器中，之后也可以将server中的私钥删除掉
    （6）将私钥放在登录机（以win10为例是C盘中）当前用户路径下.ssh中，且修改id_rsa为id_rsa.myrsa，以做区别
    （7）修改.ssh/config文件，添加如下内容，注意缩进：
            Host 10.28.120.60               // ssh server ip地址
	            HostName 10.28.120.60       // ssh server ip地址或者server主机名称
	            User jsn                    // 通过该ssh key要登录进ssh server主机的用户的用户名
	            IdentityFile ~/.ssh/id_rsa.jsnwebapp   // 当前登录机中的对应私钥文件地址
    （8）修改.ssh/known_hosts文件，添加如下内容：
            [server ip地址]:ssh服务端口（默认是22）  ssh-rsa 私钥的内容  server主机用户名@server主机名称
            [10.28.120.60]:22 ssh-rsa AAAAB3NzaC******  jsn@jsn-machine
    （9）重启ssh server：sudo /etc/init.d/ssh restart   完成ssh配置

    Note：在新增私钥的时候，通过指定不同的文件名来生成不同的私钥文件，以方便同时管理多个私钥
        ssh-keygen -t rsa -f ~/.ssh/id_rsa.work -C "Key for Work stuff"
        ssh-keygen -t rsa -f ~/.ssh/id_rsa.github -C "Key for GitHub stuff"

3. 安装nginx supervisor  mysql-server 应用/服务
    sudo apt-get install nginx supervisor python3 mysql-server  //不确定这里的python3有什么用，也可以使用下面的命令：
    sudo apt-get install nginx supervisor mysql-server     //推荐使用这个命令
    安装mysql的时候要注意设置root密码（可能会有提示，也可能没有提示）：
        （1）有提示，则直接设置root密码即可
        （2）若没有提示：
                A. sudo vim /etc/mysql/debian.cnf
                        在debian.cnf中找到[client]下的user和password的值并记录下来，这是默认用户名和密码
                B. 使用默认用户名和密码登录，进入mysql：
                        mysql -u user -p 输入记录的password
                C. 重置密码（此处设置为 111）
                        update mysql.user set authentication_string=password('111') where user='root' and Host='localhost';
                        exit //退出mysql
                D. 重启mysql服务：
                        service mysqld restart
                    或  /etc/inint.d/mysqld restart

4. 安装Python3的所需要的库：jinja2 aiomysql aiohttp
    sudo pip3 install jinja2 aiomysql aiohttp

5. 在服务器上创建目录/srv/jsnwebapp/以及相应的子目录。

6. 在服务器上初始化MySQL数据库，把数据库初始化脚本schema.sql复制到服务器上执行：
    mysql -u root -p < schema.sql

7. 在开发机上安装Fabric，服务器上不需要安装Fabric，Fabric使用SSH直接登录服务器并执行部署命令，推荐使用Fabric3
    （1）Fabric 1.x 只支持Python2.5-2.7， 
         Fabric3支持Python（2.7，3.4+）;
         Fabric 2.x 只支持Python3，是重写Fabric 1.x的版本，不再兼容1.x 版本的fabfile，而且有些模块和用法也发生了很大改变；
    （2）安装Fabric3之前要将旧的Fabric卸载掉： pip/pip2/pip3 uninstall fabric
        为Python3安装Fabric3（因为我的开发机是Win10，用的是Python3.6）：pip3 install fabric3 --proxy="10.144.1.10:8080"
        或 使用： pip3 install fabric3

    （3） fab命令执行时，默认引用一个名为fabfile.py的文件，我们也可以通过-f来进行指定(文件名不能为abc.py，会冲突).
            所以可以将部署相关function写在fabfile.py中，使用fab命令默认执行；也可以自定义.py文件， 通过fab -f 来指定该文件
    其他具体内容可以参考 /fabfile.py

8. 虚拟机的网络要配置为桥接
    以VirtualBox为例，虚拟机网络要设置为桥接网卡；网卡配置的高级选项中 混杂模式配置为：全部允许， 接入网线 要打勾；

9. 按照 /fabfile.py 中描述配置完成后，可能会需要配置服务器的防火墙（要单独去解决了），但是默认可能是关闭的就不需要处理防火墙了
    配置完成后可能会出现奇怪的现象，服务器自己的浏览器直接访问IP有时会成功，有时会只显示Nginx的welcome信息
    并且，在开发机（同IP网段的其他机器）的浏览器直接访问IP也会出现 有时访问成功，有时只显示Nginx的welcome信息
    目前还不确定是什么原因；

    甚至，刚开始访问失败，过了两天（没有关闭虚拟机），再次访问的时候，竟然成功了（并且是从开发机的浏览器访问的！！）
    真是百思不得解啊！

